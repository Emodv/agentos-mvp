// Package fetch provides an outbound HTTP client hardened against
// SSRF: only http/https, public IPs only (checked at dial time so DNS
// rebinding can't bypass it), capped response size, and timeouts.
package fetch

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"syscall"
	"time"
)

const (
	// MaxBodyBytes caps how much of a remote response we read.
	MaxBodyBytes = 5 << 20 // 5 MB
	userAgent    = "L2Agent/1.0 (+https://github.com/Emodv/l2agent)"
)

var ErrBlockedAddress = errors.New("destination address is not allowed")

// Client is an http.Client that refuses to connect to private,
// loopback, link-local, or otherwise non-public addresses.
var Client = &http.Client{
	Timeout: 20 * time.Second,
	Transport: &http.Transport{
		DialContext: (&net.Dialer{
			Timeout: 10 * time.Second,
			// Control runs after DNS resolution, immediately before
			// connect, so the check applies to the real target IP.
			Control: func(network, address string, _ syscall.RawConn) error {
				host, _, err := net.SplitHostPort(address)
				if err != nil {
					return err
				}
				ip := net.ParseIP(host)
				if ip == nil || !isPublicIP(ip) {
					return fmt.Errorf("%w: %s", ErrBlockedAddress, host)
				}
				return nil
			},
		}).DialContext,
		MaxIdleConns:        50,
		IdleConnTimeout:     60 * time.Second,
		TLSHandshakeTimeout: 10 * time.Second,
	},
	CheckRedirect: func(req *http.Request, via []*http.Request) error {
		if len(via) >= 5 {
			return errors.New("too many redirects")
		}
		return nil
	},
}

func isPublicIP(ip net.IP) bool {
	return !(ip.IsLoopback() ||
		ip.IsPrivate() ||
		ip.IsLinkLocalUnicast() ||
		ip.IsLinkLocalMulticast() ||
		ip.IsMulticast() ||
		ip.IsUnspecified())
}

// ValidateURL rejects anything that is not a plain http(s) URL with a host.
func ValidateURL(raw string) (*url.URL, error) {
	u, err := url.Parse(strings.TrimSpace(raw))
	if err != nil {
		return nil, fmt.Errorf("invalid url: %w", err)
	}
	if u.Scheme != "http" && u.Scheme != "https" {
		return nil, fmt.Errorf("unsupported scheme %q (only http/https)", u.Scheme)
	}
	if u.Host == "" {
		return nil, errors.New("url has no host")
	}
	return u, nil
}

// Get fetches a URL safely and returns at most MaxBodyBytes of the body.
func Get(ctx context.Context, rawURL string) (body []byte, status int, err error) {
	u, err := ValidateURL(rawURL)
	if err != nil {
		return nil, 0, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u.String(), nil)
	if err != nil {
		return nil, 0, err
	}
	req.Header.Set("User-Agent", userAgent)
	req.Header.Set("Accept", "text/html,application/xhtml+xml,*/*")

	resp, err := Client.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()

	data, err := io.ReadAll(io.LimitReader(resp.Body, MaxBodyBytes))
	if err != nil {
		return nil, resp.StatusCode, err
	}
	return data, resp.StatusCode, nil
}

// PostForm submits form-encoded fields to a URL with the same protections.
func PostForm(ctx context.Context, rawURL string, fields map[string]string) (body []byte, status int, err error) {
	u, err := ValidateURL(rawURL)
	if err != nil {
		return nil, 0, err
	}
	form := url.Values{}
	for k, v := range fields {
		form.Set(k, v)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, u.String(), strings.NewReader(form.Encode()))
	if err != nil {
		return nil, 0, err
	}
	req.Header.Set("User-Agent", userAgent)
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")

	resp, err := Client.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()

	data, err := io.ReadAll(io.LimitReader(resp.Body, MaxBodyBytes))
	if err != nil {
		return nil, resp.StatusCode, err
	}
	return data, resp.StatusCode, nil
}
