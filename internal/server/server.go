// Package server exposes the L2Agent HTTP API:
//
//	GET  /healthz              – liveness probe
//	GET  /v1/analyze?url=...   – fetch URL and return structured JSON
//	POST /v1/analyze           – parse raw HTML body and return structured JSON
//	POST /v1/submit            – form submission
//	GET  /v1/stats[?agent_id=] – usage stats (all agents or one)
package server

import (
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/Emodv/l2agent/internal/analyzer"
	"github.com/Emodv/l2agent/internal/fetch"
	"github.com/Emodv/l2agent/internal/store"
)

const (
	rateLimitPerMin = 60
	cacheTTL        = 10 * time.Minute
)

type Server struct {
	store store.Store

	mu      sync.Mutex
	buckets map[string]*bucket
}

type bucket struct {
	windowStart time.Time
	count       int
}

func New(st store.Store) *Server {
	s := &Server{store: st, buckets: make(map[string]*bucket)}
	go s.cleanupBuckets()
	return s
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", s.handleHealth)
	mux.HandleFunc("GET /v1/analyze", s.protect(s.handleAnalyze))
	mux.HandleFunc("POST /v1/analyze", s.protect(s.handleAnalyzeHTML))
	mux.HandleFunc("POST /v1/submit", s.protect(s.handleSubmit))
	mux.HandleFunc("GET /v1/stats", s.protect(s.handleStats))
	// Back-compat with the original /scrape contract.
	mux.HandleFunc("POST /scrape", s.protect(s.handleScrape))
	return corsMiddleware(mux)
}

func (s *Server) protect(h http.HandlerFunc) http.HandlerFunc {
	return s.rateLimit(apiKeyMiddleware(h))
}

// ── Middleware ────────────────────────────────────────────

func corsMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-API-Key, X-Agent-ID")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// apiKeyMiddleware enforces X-API-Key only when L2AGENT_API_KEY is set.
// Keys are accepted from the header only — never query params, which
// leak into logs.
func apiKeyMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		want := os.Getenv("L2AGENT_API_KEY")
		if want == "" {
			next(w, r)
			return
		}
		got := r.Header.Get("X-API-Key")
		if subtle.ConstantTimeCompare([]byte(got), []byte(want)) != 1 {
			writeError(w, http.StatusUnauthorized, "invalid or missing API key")
			return
		}
		next(w, r)
	}
}

// rateLimit applies a fixed window per client IP. The IP comes from
// X-Forwarded-For (set by the hosting edge proxy) or RemoteAddr — not
// from caller-supplied agent IDs, which would be trivially spoofable.
func (s *Server) rateLimit(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ip := clientIP(r)
		now := time.Now()

		s.mu.Lock()
		b, ok := s.buckets[ip]
		if !ok || now.Sub(b.windowStart) > time.Minute {
			b = &bucket{windowStart: now}
			s.buckets[ip] = b
		}
		b.count++
		over := b.count > rateLimitPerMin
		s.mu.Unlock()

		if over {
			writeError(w, http.StatusTooManyRequests, "rate limit exceeded (60 req/min)")
			return
		}
		next(w, r)
	}
}

func (s *Server) cleanupBuckets() {
	for range time.Tick(5 * time.Minute) {
		s.mu.Lock()
		for ip, b := range s.buckets {
			if time.Since(b.windowStart) > 2*time.Minute {
				delete(s.buckets, ip)
			}
		}
		s.mu.Unlock()
	}
}

func clientIP(r *http.Request) string {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		if i := strings.IndexByte(xff, ','); i > 0 {
			return strings.TrimSpace(xff[:i])
		}
		return strings.TrimSpace(xff)
	}
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}

// ── Handlers ──────────────────────────────────────────────

func (s *Server) handleHealth(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok", "store": s.store.Name()})
}

func (s *Server) analyze(ctx context.Context, rawURL, agentID string) ([]byte, error) {
	cacheKey := hashKey(rawURL)
	if cached, ok := s.store.CacheGet(cacheKey); ok {
		return cached, nil
	}

	body, status, err := fetch.Get(ctx, rawURL)
	if err != nil {
		return nil, err
	}
	if status != http.StatusOK {
		return nil, fmt.Errorf("upstream returned status %d", status)
	}

	html := string(body)
	page, err := analyzer.Analyze(strings.NewReader(html), rawURL)
	if err != nil {
		return nil, fmt.Errorf("parse failed: %w", err)
	}

	// Serialize once without meta to measure output size, then attach
	// the measured accounting and serialize the final payload.
	draft, _ := json.Marshal(page)
	page.FillMeta(html, string(draft))
	out, err := json.Marshal(page)
	if err != nil {
		return nil, err
	}

	if agentID != "" {
		if err := s.store.RecordRequest(agentID, page.Meta.RawTokens, page.Meta.OptimizedTokens); err != nil {
			log.Printf("stats record failed for agent=%s: %v", agentID, err)
		}
	}
	s.store.CacheSet(cacheKey, out, cacheTTL)
	return out, nil
}

func (s *Server) handleAnalyze(w http.ResponseWriter, r *http.Request) {
	rawURL := r.URL.Query().Get("url")
	if rawURL == "" {
		writeError(w, http.StatusBadRequest, "url query parameter is required")
		return
	}
	agentID := agentIDFrom(r, r.URL.Query().Get("agent_id"))

	out, err := s.analyze(r.Context(), rawURL, agentID)
	if err != nil {
		writeFetchError(w, err)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Write(out)
}

// handleAnalyzeHTML accepts raw HTML in the request body and parses it
// in-process — no outbound network fetch is performed. This is useful
// when the caller already holds the HTML (e.g. from a browser extension
// or another fetch layer) and just wants structured extraction.
func (s *Server) handleAnalyzeHTML(w http.ResponseWriter, r *http.Request) {
	pageURL := r.URL.Query().Get("url") // optional: used for resolving relative links
	agentID := agentIDFrom(r, r.URL.Query().Get("agent_id"))

	body, err := io.ReadAll(io.LimitReader(r.Body, fetch.MaxBodyBytes))
	if err != nil || len(body) == 0 {
		writeError(w, http.StatusBadRequest, "request body must contain HTML")
		return
	}

	html := string(body)
	page, err := analyzer.Analyze(strings.NewReader(html), pageURL)
	if err != nil {
		writeError(w, http.StatusUnprocessableEntity, "parse failed: "+err.Error())
		return
	}

	draft, _ := json.Marshal(page)
	page.FillMeta(html, string(draft))
	out, err := json.Marshal(page)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "marshal failed")
		return
	}

	if agentID != "" {
		if err := s.store.RecordRequest(agentID, page.Meta.RawTokens, page.Meta.OptimizedTokens); err != nil {
			log.Printf("stats record failed for agent=%s: %v", agentID, err)
		}
	}

	w.Header().Set("Content-Type", "application/json")
	w.Write(out)
}

// handleScrape preserves the original POST /scrape API shape.
func (s *Server) handleScrape(w http.ResponseWriter, r *http.Request) {
	var req struct {
		URL     string `json:"url"`
		AgentID string `json:"agent_id"`
	}
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}
	if req.URL == "" {
		writeError(w, http.StatusBadRequest, "url is required")
		return
	}
	out, err := s.analyze(r.Context(), req.URL, agentIDFrom(r, req.AgentID))
	if err != nil {
		writeFetchError(w, err)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Write(out)
}

func (s *Server) handleSubmit(w http.ResponseWriter, r *http.Request) {
	var req struct {
		URL     string            `json:"url"`
		Fields  map[string]string `json:"fields"`
		AgentID string            `json:"agent_id"`
	}
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 1<<20)).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}
	if req.URL == "" || len(req.Fields) == 0 {
		writeError(w, http.StatusBadRequest, "url and fields are required")
		return
	}

	body, status, err := fetch.PostForm(r.Context(), req.URL, req.Fields)
	if err != nil {
		writeFetchError(w, err)
		return
	}

	agentID := agentIDFrom(r, req.AgentID)
	if agentID != "" {
		raw := analyzer.EstimateTokens(string(body))
		if err := s.store.RecordRequest(agentID, raw, analyzer.EstimateTokens("")+50); err != nil {
			log.Printf("stats record failed for agent=%s: %v", agentID, err)
		}
	}

	snippet := string(body)
	if len(snippet) > 500 {
		snippet = snippet[:500]
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"success":     status >= 200 && status < 300,
		"status_code": status,
		"agent_id":    agentID,
		"timestamp":   time.Now().UTC(),
		"response":    snippet,
	})
}

func (s *Server) handleStats(w http.ResponseWriter, r *http.Request) {
	if agentID := r.URL.Query().Get("agent_id"); agentID != "" {
		stats, err := s.store.GetStats(agentID)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "stats lookup failed")
			return
		}
		writeJSON(w, http.StatusOK, stats)
		return
	}
	all, err := s.store.GetAllAgentStats()
	if err != nil {
		writeError(w, http.StatusInternalServerError, "stats lookup failed")
		return
	}
	if all == nil {
		all = []*store.AgentStats{}
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"agents": all, "count": len(all)})
}

// ── Helpers ───────────────────────────────────────────────

func agentIDFrom(r *http.Request, bodyValue string) string {
	if bodyValue != "" {
		return bodyValue
	}
	return r.Header.Get("X-Agent-ID")
}

func hashKey(rawURL string) string {
	sum := sha256.Sum256([]byte(rawURL))
	return hex.EncodeToString(sum[:])
}

func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

func writeFetchError(w http.ResponseWriter, err error) {
	switch {
	case errors.Is(err, fetch.ErrBlockedAddress):
		writeError(w, http.StatusForbidden, "destination address is not allowed")
	case errors.Is(err, context.DeadlineExceeded):
		writeError(w, http.StatusGatewayTimeout, "upstream fetch timed out")
	default:
		writeError(w, http.StatusBadGateway, "fetch failed: "+err.Error())
	}
}

// ListenAndServe starts the API on the given port with sane timeouts.
func (s *Server) ListenAndServe(port string) error {
	srv := &http.Server{
		Addr:              ":" + port,
		Handler:           s.Handler(),
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       30 * time.Second,
		WriteTimeout:      60 * time.Second,
		IdleTimeout:       120 * time.Second,
	}
	log.Printf("L2Agent API listening on :%s (store=%s)", port, s.store.Name())
	return srv.ListenAndServe()
}
