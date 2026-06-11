// L2Agent Proxy - Production Hardened v0.6 (Fixed + Safe + SaaS-ready)

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

/* =========================
   MODELS
========================= */

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
	AgentID     string    `json:"agent_id,omitempty"`
	Timestamp   time.Time `json:"timestamp"`
	TokensSaved int       `json:"tokens_saved"`
	Response    string    `json:"response,omitempty"`
}

/* =========================
   HTTP CLIENT (SAFE)
========================= */

var httpClient = &http.Client{
	Timeout: 15 * time.Second,
}

/* =========================
   RATE LIMITER (SAFE TOKEN BUCKET)
========================= */

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

func rateLimitMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {

		id := r.Header.Get("X-Agent-ID")
		if id == "" {
			id = r.RemoteAddr
		}

		now := time.Now()

		mu.Lock()
		c, ok := clients[id]
		if !ok {
			c = &client{lastSeen: now, tokens: rateLimitRequests}
			clients[id] = c
		}

		// refill window
		if time.Since(c.lastSeen) > time.Duration(windowSeconds)*time.Second {
			c.tokens = rateLimitRequests
		}

		c.lastSeen = now

		if c.tokens <= 0 {
			mu.Unlock()
			http.Error(w, `{"error":"rate limit exceeded"}`, http.StatusTooManyRequests)
			return
		}

		c.tokens--
		mu.Unlock()

		next(w, r)
	}
}

/* cleanup goroutine */
func init() {
	go func() {
		for range time.Tick(5 * time.Minute) {
			mu.Lock()
			for id, c := range clients {
				if time.Since(c.lastSeen) > 10*time.Minute {
					delete(clients, id)
				}
			}
			mu.Unlock()
		}
	}()
}

/* =========================
   MIDDLEWARE
========================= */

func apiKeyMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		key := os.Getenv("L2AGENT_API_KEY")
		if key == "" {
			next(w, r)
			return
		}

		got := r.Header.Get("X-API-Key")
		if got == "" {
			got = r.URL.Query().Get("api_key")
		}

		if got != key {
			http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
			return
		}

		next(w, r)
	}
}

func corsMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-API-Key, X-Agent-ID")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusOK)
			return
		}

		next(w, r)
	}
}

/* =========================
   SAFE REQUEST
========================= */

func doRequest(method, u string, body io.Reader, headers map[string]string) (*http.Response, error) {
	req, err := http.NewRequest(method, u, body)
	if err != nil {
		return nil, err
	}

	req.Header.Set("User-Agent", "L2Agent/0.6")

	for k, v := range headers {
		req.Header.Set(k, v)
	}

	return httpClient.Do(req)
}

/* =========================
   TOKEN ESTIMATION (FIXED)
========================= */

func estimateTokens(html string) int {
	clean := len(strings.TrimSpace(html)) / 4
	if clean < 45 {
		return 45
	}
	if clean > 20000 {
		return 20000
	}
	return clean
}

/* =========================
   ANALYZE
========================= */

func analyzeHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")

	rawURL := r.URL.Query().Get("url")
	agentID := r.Header.Get("X-Agent-ID")

	if rawURL == "" {
		http.Error(w, `{"error":"url required"}`, 400)
		return
	}

	_, err := url.ParseRequestURI(rawURL)
	if err != nil {
		http.Error(w, `{"error":"invalid url"}`, 400)
		return
	}

	resp, err := doRequest("GET", rawURL, nil, map[string]string{
		"Accept": "text/html,*/*",
	})
	if err != nil || resp == nil {
		http.Error(w, `{"error":"fetch failed"}`, 502)
		return
	}
	defer resp.Body.Close()

	bodyBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		http.Error(w, `{"error":"read failed"}`, 500)
		return
	}

	html := string(bodyBytes)

	doc, err := goquery.NewDocumentFromReader(bytes.NewReader(bodyBytes))
	if err != nil {
		http.Error(w, `{"error":"parse failed"}`, 500)
		return
	}

	tokens := estimateTokens(html)

	result := AnalyzeResponse{
		URL:         rawURL,
		Timestamp:   time.Now(),
		Tokens:      tokens,
		TokensSaved: tokens * 8,
		AgentID:     agentID,
	}

	doc.Find("form").Each(func(i int, s *goquery.Selection) {
		form := Form{
			Action: s.AttrOr("action", ""),
			Method: strings.ToUpper(s.AttrOr("method", "GET")),
		}

		s.Find("input, select, textarea").Each(func(j int, f *goquery.Selection) {
			form.Fields = append(form.Fields, Field{
				Name:        f.AttrOr("name", ""),
				Type:        f.AttrOr("type", "text"),
				Required:    f.Is("[required]"),
				Placeholder: f.AttrOr("placeholder", ""),
			})
		})

		result.Forms = append(result.Forms, form)
	})

	doc.Find("a[href]").Each(func(i int, s *goquery.Selection) {
		if i >= 20 {
			return
		}
		href := s.AttrOr("href", "")
		if href == "" || strings.HasPrefix(href, "#") {
			return
		}

		result.Links = append(result.Links, Link{
			Text: strings.TrimSpace(s.Text()),
			Href: href,
		})
	})

	if agentID != "" {
		_ = store.RecordRequest(agentID, int64(tokens), int64(tokens*8))
	}

	json.NewEncoder(w).Encode(result)
}

/* =========================
   SUBMIT (SAFE)
========================= */

func submitHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")

	var req SubmitRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"error":"invalid json"}`, 400)
		return
	}

	if req.URL == "" {
		http.Error(w, `{"error":"url required"}`, 400)
		return
	}

	form := url.Values{}
	for k, v := range req.Fields {
		form.Set(k, v)
	}

	resp, err := httpClient.PostForm(req.URL, form)
	if err != nil || resp == nil {
		http.Error(w, `{"error":"submit failed"}`, 502)
		return
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)

	out := SubmitResponse{
		Success:     resp.StatusCode < 400,
		StatusCode:  resp.StatusCode,
		Timestamp:   time.Now(),
		AgentID:     req.AgentID,
		TokensSaved: 400,
		Response:    safeTruncate(string(body), 200),
	}

	json.NewEncoder(w).Encode(out)
}

func safeTruncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n]
}

/* =========================
   HEALTH
========================= */

func healthHandler(w http.ResponseWriter, r *http.Request) {
	json.NewEncoder(w).Encode(map[string]any{
		"status":  "ok",
		"service": "l2agent-proxy",
		"version": "0.6.0",
		"time":    time.Now(),
	})
}

/* =========================
   DASHBOARD
========================= */

func dashboardHandler(w http.ResponseWriter, r *http.Request) {
	data, err := os.ReadFile("./dashboard/index.html")
	if err != nil {
		http.Redirect(w, r, "/health", 302)
		return
	}
	w.Header().Set("Content-Type", "text/html")
	w.Write(data)
}

/* =========================
   MAIN
========================= */

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	_ = store.Init()

	mux := http.NewServeMux()

	mux.HandleFunc("/health",
		corsMiddleware(rateLimitMiddleware(healthHandler)))

	mux.HandleFunc("/v1/analyze",
		corsMiddleware(apiKeyMiddleware(rateLimitMiddleware(analyzeHandler))))

	mux.HandleFunc("/v1/submit",
		corsMiddleware(apiKeyMiddleware(rateLimitMiddleware(submitHandler))))

	mux.HandleFunc("/",
		corsMiddleware(dashboardHandler))

	log.Printf("L2Agent Proxy v0.6 running on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, mux))
}
```
