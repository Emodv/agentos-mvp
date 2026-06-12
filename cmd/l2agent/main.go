// L2Agent – structured web access for AI agents.
//
// Usage:
//
//	l2agent serve     Start the HTTP API (default, port from $PORT or 8080)
//	l2agent gateway   Start the MCP stdio gateway
package main

import (
	"fmt"
	"log"
	"os"

	"github.com/Emodv/l2agent/internal/mcp"
	"github.com/Emodv/l2agent/internal/server"
	"github.com/Emodv/l2agent/internal/store"
)

func main() {
	log.SetOutput(os.Stderr)

	cmd := "serve"
	if len(os.Args) > 1 {
		cmd = os.Args[1]
	}

	st := openStore()

	switch cmd {
	case "serve", "proxy":
		port := os.Getenv("PORT")
		if port == "" {
			port = "8080"
		}
		srv := server.New(st)
		log.Fatal(srv.ListenAndServe(port))

	case "gateway":
		log.Println("L2Agent MCP gateway started (stdio)")
		if err := mcp.NewGateway(st).Run(os.Stdin, os.Stdout); err != nil {
			log.Fatalf("gateway error: %v", err)
		}

	case "version":
		fmt.Println("l2agent 1.0.0")

	default:
		fmt.Fprintf(os.Stderr, "unknown command %q\nusage: l2agent [serve|gateway|version]\n", cmd)
		os.Exit(2)
	}
}

// openStore uses Redis when REDIS_URL is set and reachable, and falls
// back to in-memory so the binary always works out of the box.
func openStore() store.Store {
	redisURL := os.Getenv("REDIS_URL")
	if redisURL == "" {
		log.Println("REDIS_URL not set — using in-memory store (stats reset on restart)")
		return store.NewMemoryStore()
	}
	rs, err := store.NewRedisStore(redisURL)
	if err != nil {
		log.Printf("redis unavailable (%v) — falling back to in-memory store", err)
		return store.NewMemoryStore()
	}
	log.Println("connected to redis")
	return rs
}
