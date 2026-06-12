package store

import (
	"context"
	"fmt"
	"strconv"
	"time"

	"github.com/redis/go-redis/v9"
)

type RedisStore struct {
	rdb *redis.Client
}

// NewRedisStore connects to Redis using a redis:// URL. It returns an
// error (instead of crashing later) if the server is unreachable.
func NewRedisStore(redisURL string) (*RedisStore, error) {
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, fmt.Errorf("invalid REDIS_URL: %w", err)
	}
	rdb := redis.NewClient(opt)
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	if err := rdb.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("redis connection failed: %w", err)
	}
	return &RedisStore{rdb: rdb}, nil
}

func (r *RedisStore) Name() string { return "redis" }

func (r *RedisStore) RecordRequest(agentID string, rawTokens, optimizedTokens int) error {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	key := "agent:" + agentID
	pipe := r.rdb.Pipeline()
	pipe.HIncrBy(ctx, key, "total_requests", 1)
	pipe.HIncrBy(ctx, key, "raw_tokens", int64(rawTokens))
	pipe.HIncrBy(ctx, key, "optimized_tokens", int64(optimizedTokens))
	pipe.HSet(ctx, key, "last_seen", time.Now().UTC().Format(time.RFC3339))
	pipe.Expire(ctx, key, 90*24*time.Hour)
	_, err := pipe.Exec(ctx)
	return err
}

func (r *RedisStore) GetStats(agentID string) (*AgentStats, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	vals, err := r.rdb.HGetAll(ctx, "agent:"+agentID).Result()
	if err != nil {
		return nil, err
	}
	stats := &AgentStats{AgentID: agentID}
	if len(vals) == 0 {
		return stats, nil
	}
	stats.TotalRequests, _ = strconv.ParseInt(vals["total_requests"], 10, 64)
	stats.RawTokens, _ = strconv.ParseInt(vals["raw_tokens"], 10, 64)
	stats.OptimizedTokens, _ = strconv.ParseInt(vals["optimized_tokens"], 10, 64)
	stats.LastSeen = vals["last_seen"]
	return finalize(stats), nil
}

func (r *RedisStore) GetAllAgentStats() ([]*AgentStats, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	var all []*AgentStats
	// SCAN instead of KEYS so we never block Redis on large keyspaces.
	iter := r.rdb.Scan(ctx, 0, "agent:*", 100).Iterator()
	for iter.Next(ctx) {
		agentID := iter.Val()[len("agent:"):]
		stats, err := r.GetStats(agentID)
		if err == nil {
			all = append(all, stats)
		}
	}
	if err := iter.Err(); err != nil {
		return nil, err
	}
	return all, nil
}

func (r *RedisStore) CacheGet(key string) ([]byte, bool) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	val, err := r.rdb.Get(ctx, "cache:"+key).Bytes()
	if err != nil {
		return nil, false
	}
	return val, true
}

func (r *RedisStore) CacheSet(key string, value []byte, ttl time.Duration) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	r.rdb.Set(ctx, "cache:"+key, value, ttl)
}
