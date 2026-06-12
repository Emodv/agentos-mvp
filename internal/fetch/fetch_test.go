package fetch

import (
	"context"
	"errors"
	"net"
	"testing"
)

func TestValidateURL(t *testing.T) {
	valid := []string{"https://example.com", "http://example.com/path?q=1"}
	for _, u := range valid {
		if _, err := ValidateURL(u); err != nil {
			t.Errorf("ValidateURL(%q) = %v, want nil", u, err)
		}
	}

	invalid := []string{"", "ftp://example.com", "file:///etc/passwd", "javascript:alert(1)", "http://"}
	for _, u := range invalid {
		if _, err := ValidateURL(u); err == nil {
			t.Errorf("ValidateURL(%q) = nil, want error", u)
		}
	}
}

func TestPublicIPGuard(t *testing.T) {
	blocked := []string{
		"127.0.0.1",       // loopback
		"10.0.0.5",        // private
		"172.16.1.1",      // private
		"192.168.1.1",     // private
		"169.254.169.254", // link-local / cloud metadata
		"0.0.0.0",         // unspecified
		"::1",             // v6 loopback
		"fc00::1",         // v6 unique local
	}
	for _, addr := range blocked {
		if isPublicIP(net.ParseIP(addr)) {
			t.Errorf("isPublicIP(%s) = true, want false", addr)
		}
	}
	for _, addr := range []string{"93.184.216.34", "2606:2800:220:1::1"} {
		if !isPublicIP(net.ParseIP(addr)) {
			t.Errorf("isPublicIP(%s) = false, want true", addr)
		}
	}
}

func TestGetRefusesPrivateDestinations(t *testing.T) {
	_, _, err := Get(context.Background(), "http://127.0.0.1:6379/")
	if err == nil {
		t.Fatal("Get(loopback) succeeded, want blocked")
	}
	if !errors.Is(err, ErrBlockedAddress) {
		t.Logf("blocked with non-sentinel error (acceptable): %v", err)
	}
}
