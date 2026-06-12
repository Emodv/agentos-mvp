// L2Agent Proxy - Enhanced v0.5
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/PuerkitoBio/goquery"
	"github.com/Emodv/l2agent/internal/store"
)

type AnalyzeResponse struct {
	URL         string    `json:"url"`
	Forms       []Form    `json:"forms"`
	Links       []Link    `json:"links"`
	Timestamp   time.Time `json:"timestamp"`
	AgentID     string    `json:"agent_id,omitempty"`
	Tokens      int       `json:"estimated_tokens"`
	TokensSaved int       `json:"tokens_saved"`
}

type Form struct {
	Action string  `json:"action"`
	Method string  `json:"method"`
	Fields []Field `json:"fields"`
}

type Field struct {
	Name        string `json:"name"`
	Type        string `json:"type"`
	Required    bool   `json:"required"`
	Placeholder string `json:"placeholder,omitempty"`
}

type Link struct {
	Text string `json:"text"`
	Href string `json:"href"`
}

type SubmitRequest struct {
	URL     string            `json:"url"`
	Fields  map[string]string `json:"fields"`
	AgentID string            `json:"agent_id"`
}

type SubmitResponse struct {
	Success     bool      `json:"success"`
	StatusCode  int       `json:"status_code"`
	AgentID     string    `json:"agent_id"`
	Timestamp   time.Time `json:"timestamp"`
	TokensSaved int       `json:"tokens_saved"`
	Response    string    `json:"response,omitempty"`
}

// Rate limiter
type client struct {
	lastSeen time.Time
	tokens   int
}

var (
	mu      sync.Mutex
	clients = make(map[string]*client)
)

const (
	rateLimitRequests = 10
	windowSeconds     = 60
)

var httpClient = &http.Client{Timeout: 15 * time.Second}

func init() { go cleanupRateLimiter() }

func cleanupRateLimiter() {
	for range time.Tick(5 * time.Minute) {
		mu.Lock()
		now := time.Now()
		for id, c := range clients {
			if time.Since(c.lastSeen) > 2*time.Duration(windowSeconds)*time.Second {
				delete(clients, id)
			}
		}
		mu.Unlock()
	}
}

func rateLimitMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := r.Header.Get("X-Agent-ID")
		if id == "" { id = r.RemoteAddr }

		mu.Lock()
		c, ok := clients[id]
		if !ok {
			c = &client{lastSeen: time.Now(), tokens: rateLimitRequests}
			clients[id] = c
		}

		if time.Since(c.lastSeen) > time.Duration(windowSeconds)*time.Second {
			c.tokens = rateLimitRequests
		}
		c.lastSeen = time.Now()

		if c.tokens <= 0 {
			mu.Unlock()
			http.Error(w, `{"error":"rate limit exceeded"}`, 429)
			return
		}
		c.tokens--
		mu.Unlock()

		next(w, r)
	}
}

func doRequest(method, u string, body io.Reader, extraHeaders map[string]string) (*http.Response, error) {
	req, _ := http.NewRequest(method, u, body)
	req.Header.Set("User-Agent", "L2Agent/0.5")
	for k, v := range extraHeaders { req.Header.Set(k, v) }
	return httpClient.Do(req)
}

func estimateTokens(html string) int {
	words := len(strings.Fields(html))
	t := words / 2
	if t < 45 { t = 45 }
	if t > 20000 { t = 20000 }
	return t
}

// Handlers (simplified + robust)
func analyzeHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	rawURL := r.URL.Query().Get("url")
	if rawURL == "" {
		http.Error(w, `{"error":"url required"}`, 400); return
	}

	resp, err := doRequest("GET", rawURL, nil, map[string]string{"Accept": "text/html,*/*"})
	if err != nil || resp.StatusCode != 200 {
		http.Error(w, `{"error":"fetch failed"}`, 502); return
	}
	defer resp.Body.Close()

	bodyBytes, _ := io.ReadAll(resp.Body)
	html := string(bodyBytes)
	doc, _ := goquery.NewDocumentFromReader(bytes.NewReader(bodyBytes))

	result := AnalyzeResponse{
		URL: rawURL, Timestamp: time.Now(),
		Tokens: estimateTokens(html), TokensSaved: estimateTokens(html) * 8,
	}

	// forms + links (existing logic kept)
	doc.Find("form").Each(func(_ int, s *goquery.Selection) {
		// ... (keep your form extraction)
		form := Form{Action: s.AttrOr("action", ""), Method: strings.ToUpper(s.AttrOr("method", "GET"))}
		// fields...
		result.Forms = append(result.Forms, form)
	})

	doc.Find("a[href]").Each(func(i int, s *goquery.Selection) {
		if i >= 20 { return }
		href := s.AttrOr("href", "")
		if href != "" && !strings.HasPrefix(href, "#") {
			result.Links = append(result.Links, Link{Text: strings.TrimSpace(s.Text()), Href: href})
		}
	})

	if id := r.Header.Get("X-Agent-ID"); id != "" {
		store.RecordRequest(id, result.Tokens, result.TokensSaved)
	}

	json.NewEncoder(w).Encode(result)
}

func submitHandler(w http.ResponseWriter, r *http.Request) {
	// ... (keep decode + post logic, add small response body read)
	var req SubmitRequest
	json.NewDecoder(r.Body).Decode(&req)
	// ... post ...

	respBody, _ := io.ReadAll(resp.Body)
	json.NewEncoder(w).Encode(SubmitResponse{
		Success: resp.StatusCode < 400, StatusCode: resp.StatusCode,
		TokensSaved: 400, Response: string(respBody)[:200], // truncate
	})
}

// ... keep stats, health, dashboard ...

func main() {
	port := os.Getenv("PORT")
	if port == "" { port = "8080" }

	store.Init()
	mux := http.NewServeMux()

	mux.HandleFunc("/health", corsMiddleware(rateLimitMiddleware(healthHandler)))
	mux.HandleFunc("/v1/analyze", corsMiddleware(apiKeyMiddleware(rateLimitMiddleware(analyzeHandler))))
	mux.HandleFunc("/v1/submit", corsMiddleware(apiKeyMiddleware(rateLimitMiddleware(submitHandler))))
	mux.HandleFunc("/v1/stats", corsMiddleware(rateLimitMiddleware(statsHandler)))
	mux.HandleFunc("/", corsMiddleware(dashboardHandler))

	log.Printf("L2Agent Proxy v0.5 on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}
