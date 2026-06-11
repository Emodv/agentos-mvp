// L2Agent – Agent-Native API Layer (with Rate Limiting + Full Stack)
// Author: Emodv (https://github.com/Emodv)

package main

import (
	"encoding/json"
	"fmt"
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
}

/* =========================
   RATE LIMITER (MVP)
========================= */

type client struct {
	lastSeen time.Time
	tokens   int
}

var (
	mu      sync.Mutex
	clients = map[string]*client{}
)

const (
	rateLimitRequests = 10
	windowSeconds     = 60
	cleanupInterval   = 5 * time.Minute
)

func rateLimitMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {

		id := r.Header.Get("X-Agent-ID")
		if id == "" {
			id = r.RemoteAddr
		}

		now := time.Now()

		mu.Lock()
		c, exists := clients[id]
		if !exists {
			c = &client{lastSeen: now, tokens: rateLimitRequests}
			clients[id] = c
		}

		// refill window
		if time.Since(c.lastSeen) > time.Duration(windowSeconds)*time.Second {
			c.tokens = rateLimitRequests
			c.lastSeen = now
		}

		if c.tokens <= 0 {
			mu.Unlock()
			http.Error(w, `{"error":"rate limit exceeded"}`, http.StatusTooManyRequests)
			return
		}

		c.tokens--
		c.lastSeen = now
		mu.Unlock()

		next(w, r)
	}
}

/* =========================
   AUTH + CORS
========================= */

func apiKeyMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		apiKey := os.Getenv("L2AGENT_API_KEY")
		if apiKey == "" {
			next(w, r)
			return
		}

		provided := r.Header.Get("X-API-Key")
		if provided == "" {
			provided = r.URL.Query().Get("api_key")
		}

		if provided != apiKey {
			http.Error(w, `{"error":"invalid or missing API key"}`, http.StatusUnauthorized)
			return
		}

		next(w, r)
	}
}

func corsMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-API-Key, X-Agent-ID")

		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusOK)
			return
		}

		next(w, r)
	}
}

/* =========================
   ANALYZE ENDPOINT
========================= */

func analyzeHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")

	rawURL := r.URL.Query().Get("url")
	agentID := r.Header.Get("X-Agent-ID")

	if rawURL == "" {
		http.Error(w, `{"error":"url parameter required"}`, http.StatusBadRequest)
		return
	}

	if _, err := url.ParseRequestURI(rawURL); err != nil {
		http.Error(w, `{"error":"invalid url"}`, http.StatusBadRequest)
		return
	}

	resp, err := http.Get(rawURL)
	if err != nil {
		http.Error(w, fmt.Sprintf(`{"error":"fetch failed: %s"}`, err), http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		http.Error(w, `{"error":"html parse failed"}`, http.StatusInternalServerError)
		return
	}

	result := AnalyzeResponse{
		URL: rawURL, Timestamp: time.Now(),
		AgentID: agentID, Tokens: 45, TokensSaved: 355,
	}

	doc.Find("form").Each(func(i int, s *goquery.Selection) {
		form := Form{
			Action: s.AttrOr("action", ""),
			Method: strings.ToUpper(s.AttrOr("method", "GET")),
		}

		s.Find("input, select, textarea").Each(func(j int, field *goquery.Selection) {
			_, required := field.Attr("required")

			form.Fields = append(form.Fields, Field{
				Name:        field.AttrOr("name", ""),
				Type:        field.AttrOr("type", "text"),
				Required:    required,
				Placeholder: field.AttrOr("placeholder", ""),
			})
		})

		result.Forms = append(result.Forms, form)
	})

	doc.Find("a[href]").Each(func(i int, s *goquery.Selection) {
		if i >= 20 {
			return
		}

		result.Links = append(result.Links, Link{
			Text: strings.TrimSpace(s.Text()),
			Href: s.AttrOr("href", ""),
		})
	})

	if agentID != "" {
		_ = store.RecordRequest(agentID, 400, 45)
	}

	json.NewEncoder(w).Encode(result)
}

/* =========================
   SUBMIT ENDPOINT
========================= */

func submitHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")

	var req SubmitRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, `{"error":"invalid request body"}`, http.StatusBadRequest)
		return
	}

	if req.URL == "" {
		http.Error(w, `{"error":"url required"}`, http.StatusBadRequest)
		return
	}

	formData := url.Values{}
	for k, v := range req.Fields {
		formData.Set(k, v)
	}

	resp, err := http.PostForm(req.URL, formData)
	if err != nil {
		http.Error(w, fmt.Sprintf(`{"error":"submit failed: %s"}`, err), http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	if req.AgentID != "" {
		_ = store.RecordRequest(req.AgentID, 400, 45)
	}

	json.NewEncoder(w).Encode(SubmitResponse{
		Success:     resp.StatusCode < 400,
		StatusCode:  resp.StatusCode,
		AgentID:     req.AgentID,
		Timestamp:   time.Now(),
		TokensSaved: 355,
	})
}

/* =========================
   STATS + HEALTH + DASHBOARD
========================= */

func statsHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")

	agentID := r.URL.Query().Get("agent_id")

	if agentID != "" {
		stats, err := store.GetStats(agentID)
		if err != nil {
			http.Error(w, fmt.Sprintf(`{"error":"%s"}`, err), http.StatusInternalServerError)
			return
		}
		json.NewEncoder(w).Encode(stats)
		return
	}

	all, err := store.GetAllAgentStats()
	if err != nil {
		http.Error(w, fmt.Sprintf(`{"error":"%s"}`, err), http.StatusInternalServerError)
		return
	}

	if all == nil {
		all = []*store.AgentStats{}
	}

	var totalRequests, totalRaw, totalOptimized int64

	for _, s := range all {
		totalRequests += s.TotalRequests
		totalRaw += s.RawTokens
		totalOptimized += s.OptimizedTokens
	}

	tokensSaved := totalRaw - totalOptimized

	var savingsPct float64
	if totalRaw > 0 {
		savingsPct = float64(tokensSaved) / float64(totalRaw) * 100
	}

	const pricePerK = 0.005

	dollarWithout := float64(totalRaw) / 1000 * pricePerK
	dollarWith := float64(totalOptimized) / 1000 * pricePerK

	json.NewEncoder(w).Encode(map[string]interface{}{
		"agents": all,
		"totals": map[string]interface{}{
			"total_requests":   totalRequests,
			"raw_tokens":       totalRaw,
			"optimized_tokens": totalOptimized,
			"tokens_saved":     tokensSaved,
			"savings_pct":      savingsPct,
			"dollar_without":   dollarWithout,
			"dollar_with":      dollarWith,
			"dollar_saved":     dollarWithout - dollarWith,
		},
	})
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "ok",
		"service": "l2agent-proxy",
		"version": "0.4.0",
		"time":     time.Now(),
	})
}

func dashboardHandler(w http.ResponseWriter, r *http.Request) {
	data, err := os.ReadFile("./dashboard/index.html")
	if err != nil {
		http.Redirect(w, r, "/health", http.StatusTemporaryRedirect)
		return
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
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

	mux.HandleFunc("/v1/stats",
		corsMiddleware(rateLimitMiddleware(statsHandler)))

	mux.HandleFunc("/",
		corsMiddleware(dashboardHandler))

	log.Printf("L2Agent Proxy v0.4.0 running on :%s", port)

	log.Fatal(http.ListenAndServe(":"+port, mux))
}
```
