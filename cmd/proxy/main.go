// L2Agent – Agent-Native API Layer
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
	"time"

	"github.com/PuerkitoBio/goquery"
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

// ── Middleware ────────────────────────────────────────────

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
		w.Header().Set("Content-Type", "application/json")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusOK)
			return
		}
		next(w, r)
	}
}

// ── Handlers ──────────────────────────────────────────────

func analyzeHandler(w http.ResponseWriter, r *http.Request) {
	rawURL := r.URL.Query().Get("url")
	agentID := r.Header.Get("X-Agent-ID")
	if agentID == "" {
		agentID = r.URL.Query().Get("agent_id")
	}
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
		http.Error(w, fmt.Sprintf(`{"error":"failed to fetch: %s"}`, err), http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	doc, err := goquery.NewDocumentFromReader(resp.Body)
	if err != nil {
		http.Error(w, `{"error":"failed to parse html"}`, http.StatusInternalServerError)
		return
	}

	result := AnalyzeResponse{
		URL:         rawURL,
		Timestamp:   time.Now(),
		AgentID:     agentID,
		Tokens:      45,
		TokensSaved: 355,
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

	json.NewEncoder(w).Encode(result)
}

func submitHandler(w http.ResponseWriter, r *http.Request) {
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

	json.NewEncoder(w).Encode(SubmitResponse{
		Success:     resp.StatusCode < 400,
		StatusCode:  resp.StatusCode,
		AgentID:     req.AgentID,
		Timestamp:   time.Now(),
		TokensSaved: 355,
	})
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "ok",
		"service": "l2agent-proxy",
		"version": "0.2.0",
		"time":    time.Now(),
	})
}

// ── Main ──────────────────────────────────────────────────

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	mux := http.NewServeMux()
	mux.HandleFunc("/health", corsMiddleware(healthHandler))
	mux.HandleFunc("/v1/analyze", corsMiddleware(apiKeyMiddleware(analyzeHandler)))
	mux.HandleFunc("/v1/submit", corsMiddleware(apiKeyMiddleware(submitHandler)))

	log.Printf("L2Agent Proxy v0.2.0 running on :%s", port)
	log.Printf("Dev mode: %v", os.Getenv("L2AGENT_API_KEY") == "")

	if err := http.ListenAndServe(":"+port, mux); err != nil {
		log.Fatal(err)
	}
}
