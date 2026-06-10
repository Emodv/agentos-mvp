package store

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"time"

	"github.com/go-redis/redis/v8"
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

var rdb *redis.Client
var ctx = context.Background()

func Init() error {
	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		redisURL = "redis://localhost:6379"
	}
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return fmt.Errorf("invalid REDIS_URL: %w", err)
	}
	rdb = redis.NewClient(opt)
	_, err = rdb.Ping(ctx).Result()
	if err != nil {
		return fmt.Errorf("redis connection failed: %w", err)
	}
	return nil
}

func RecordRequest(agentID string, rawTokens int, optimizedTokens int) error {
	key := fmt.Sprintf("agent:%s", agentID)
	pipe := rdb.Pipeline()
	pipe.HIncrBy(ctx, key, "total_requests", 1)
	pipe.HIncrBy(ctx, key, "raw_tokens", int64(rawTokens))
	pipe.HIncrBy(ctx, key, "optimized_tokens", int64(optimizedTokens))
	pipe.HSet(ctx, key, "last_seen", time.Now().UTC().Format(time.RFC3339))
	pipe.Expire(ctx, key, 90*24*time.Hour)
	_, err := pipe.Exec(ctx)
	return err
}

func GetStats(agentID string) (*AgentStats, error) {
	key := fmt.Sprintf("agent:%s", agentID)
	vals, err := rdb.HGetAll(ctx, key).Result()
	if err != nil {
		return nil, err
	}
	if len(vals) == 0 {
		return &AgentStats{AgentID: agentID}, nil
	}
	stats := &AgentStats{AgentID: agentID}
	stats.TotalRequests, _ = strconv.ParseInt(vals["total_requests"], 10, 64)
	stats.RawTokens, _ = strconv.ParseInt(vals["raw_tokens"], 10, 64)
	stats.OptimizedTokens, _ = strconv.ParseInt(vals["optimized_tokens"], 10, 64)
	stats.LastSeen = vals["last_seen"]
	stats.TokensSaved = stats.RawTokens - stats.OptimizedTokens
	if stats.RawTokens > 0 {
		stats.SavingsPct = float64(stats.TokensSaved) / float64(stats.RawTokens) * 100
	}
	return stats, nil
}

func GetAllAgentStats() ([]*AgentStats, error) {
	keys, err := rdb.Keys(ctx, "agent:*").Result()
	if err != nil {
		return nil, err
	}
	var all []*AgentStats
	for _, key := range keys {
		agentID := key[len("agent:"):]
		stats, err := GetStats(agentID)
		if err == nil {
			all = append(all, stats)
		}
	}
	return all, nil
}
