// Package store persists per-agent usage stats and caches analyzed
// pages. Redis is used when REDIS_URL is set and reachable; otherwise
// an in-memory store keeps the app fully functional for local use.
package store

import (
	"sync"
	"time"
)

type AgentStats struct {
	AgentID         string  `json:"agent_id"`
	TotalRequests   int64   `json:"total_requests"`
	RawTokens       int64   `json:"raw_tokens"`
	OptimizedTokens int64   `json:"optimized_tokens"`
	TokensSaved     int64   `json:"tokens_saved"`
	SavingsPct      float64 `json:"savings_pct"`
	LastSeen        string  `json:"last_seen"`
}

type Store interface {
	RecordRequest(agentID string, rawTokens, optimizedTokens int) error
	GetStats(agentID string) (*AgentStats, error)
	GetAllAgentStats() ([]*AgentStats, error)
	CacheGet(key string) ([]byte, bool)
	CacheSet(key string, value []byte, ttl time.Duration)
	Name() string
}

func finalize(s *AgentStats) *AgentStats {
	s.TokensSaved = s.RawTokens - s.OptimizedTokens
	if s.TokensSaved < 0 {
		s.TokensSaved = 0
	}
	if s.RawTokens > 0 {
		s.SavingsPct = float64(s.TokensSaved) / float64(s.RawTokens) * 100
	}
	return s
}

// ── In-memory implementation ──────────────────────────────

type memEntry struct {
	value   []byte
	expires time.Time
}

type MemoryStore struct {
	mu    sync.Mutex
	stats map[string]*AgentStats
	cache map[string]memEntry
}

func NewMemoryStore() *MemoryStore {
	m := &MemoryStore{
		stats: make(map[string]*AgentStats),
		cache: make(map[string]memEntry),
	}
	go m.evictLoop()
	return m
}

func (m *MemoryStore) Name() string { return "memory" }

func (m *MemoryStore) RecordRequest(agentID string, rawTokens, optimizedTokens int) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	s, ok := m.stats[agentID]
	if !ok {
		s = &AgentStats{AgentID: agentID}
		m.stats[agentID] = s
	}
	s.TotalRequests++
	s.RawTokens += int64(rawTokens)
	s.OptimizedTokens += int64(optimizedTokens)
	s.LastSeen = time.Now().UTC().Format(time.RFC3339)
	return nil
}

func (m *MemoryStore) GetStats(agentID string) (*AgentStats, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	s, ok := m.stats[agentID]
	if !ok {
		return &AgentStats{AgentID: agentID}, nil
	}
	cp := *s
	return finalize(&cp), nil
}

func (m *MemoryStore) GetAllAgentStats() ([]*AgentStats, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	all := make([]*AgentStats, 0, len(m.stats))
	for _, s := range m.stats {
		cp := *s
		all = append(all, finalize(&cp))
	}
	return all, nil
}

func (m *MemoryStore) CacheGet(key string) ([]byte, bool) {
	m.mu.Lock()
	defer m.mu.Unlock()
	e, ok := m.cache[key]
	if !ok || time.Now().After(e.expires) {
		return nil, false
	}
	return e.value, true
}

func (m *MemoryStore) CacheSet(key string, value []byte, ttl time.Duration) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.cache[key] = memEntry{value: value, expires: time.Now().Add(ttl)}
}

func (m *MemoryStore) evictLoop() {
	for range time.Tick(time.Minute) {
		now := time.Now()
		m.mu.Lock()
		for k, e := range m.cache {
			if now.After(e.expires) {
				delete(m.cache, k)
			}
		}
		m.mu.Unlock()
	}
}
