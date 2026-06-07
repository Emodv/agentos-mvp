// Agent OS - Agent State Tracking
// Co-Founder & Author: Emodv

package internal

import (
	"sync"
	"time"
)

type AgentState struct {
	mu       sync.Mutex
	tokens   map[string]int      // agent_id -> total tokens used
	lastSeen map[string]time.Time
	requests map[string][]int64  // agent_id -> timestamps for rate limiting
}

func NewAgentState() *AgentState {
	return &AgentState{
		tokens:   make(map[string]int),
		lastSeen: make(map[string]time.Time),
		requests: make(map[string][]int64),
	}
}

// AddUsage increments token usage for an agent
func (a *AgentState) AddUsage(agentID string, tokensUsed int) {
	a.mu.Lock()
	defer a.mu.Unlock()
	a.tokens[agentID] += tokensUsed
	a.lastSeen[agentID] = time.Now()
}

// GetUsage returns total tokens used by agent
func (a *AgentState) GetUsage(agentID string) int {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.tokens[agentID]
}

// ResetIfNeeded resets token counter after window (e.g., daily)
func (a *AgentState) ResetIfNeeded(agentID string, window time.Duration) {
	a.mu.Lock()
	defer a.mu.Unlock()
	last := a.lastSeen[agentID]
	if time.Since(last) > window {
		a.tokens[agentID] = 0
	}
}

// RateLimit returns false if agent exceeded requests per minute
func (a *AgentState) RateLimit(agentID string, maxPerMin int) bool {
	a.mu.Lock()
	defer a.mu.Unlock()
	now := time.Now().Unix()
	// keep only last 60 seconds
	window := a.requests[agentID]
	filtered := []int64{}
	for _, ts := range window {
		if now-ts <= 60 {
			filtered = append(filtered, ts)
		}
	}
	if len(filtered) >= maxPerMin {
		return false
	}
	a.requests[agentID] = append(filtered, now)
	return true
}
