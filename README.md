# L2Agent — Structured Web Access for AI Agents

**Built for agents, not humans. Stop burning tokens on HTML noise.**

L2Agent fetches web pages and returns only what an agent needs — forms, fields, buttons, links — as compact JSON. Token savings are **measured per request** (raw HTML size vs. JSON output size) and reported honestly in every response, not as a marketing constant.

## Quick Start

```bash
# Build from source
git clone https://github.com/Emodv/l2agent && cd l2agent
make build

# Start the HTTP API (port 8080, or $PORT)
./bin/l2agent serve

# Or run the MCP gateway over stdio (for Claude Desktop / MCP clients)
./bin/l2agent gateway
```

No configuration required. If `REDIS_URL` is set, stats and the page cache persist in Redis; otherwise an in-memory store is used automatically.

## HTTP API

```bash
# Analyze a page
curl -H "X-Agent-ID: my-agent" \
  "http://localhost:8080/v1/analyze?url=https://httpbin.org/forms/post"

# Submit a form
curl -X POST http://localhost:8080/v1/submit \
  -H "Content-Type: application/json" \
  -d '{"url":"https://httpbin.org/post","fields":{"name":"Ada"},"agent_id":"my-agent"}'

# Usage stats (all agents, or ?agent_id=my-agent)
curl http://localhost:8080/v1/stats
```

Example `/v1/analyze` response:

```json
{
  "url": "https://httpbin.org/forms/post",
  "title": "Order Form",
  "forms": [
    {
      "action": "https://httpbin.org/post",
      "method": "POST",
      "fields": [
        {"name": "custname", "type": "text", "required": true},
        {"name": "custemail", "type": "email"}
      ]
    }
  ],
  "meta": {
    "raw_tokens_est": 612,
    "optimized_tokens_est": 188,
    "tokens_saved_est": 424,
    "savings_pct": 69.3,
    "note": "estimates use ~4 chars/token; raw = original HTML, optimized = this JSON"
  }
}
```

## MCP Gateway

`l2agent gateway` speaks the Model Context Protocol over stdio and exposes three tools:

| Tool | What it does |
|------|--------------|
| `analyze_url` | Fetches and parses a page in-process, returns structured JSON |
| `submit_form` | Submits form-encoded fields to a URL |
| `get_agent_stats` | Returns measured usage and savings for an agent |

Claude Desktop config example:

```json
{
  "mcpServers": {
    "l2agent": {
      "command": "/path/to/bin/l2agent",
      "args": ["gateway"]
    }
  }
}
```

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `PORT` | `8080` | HTTP listen port |
| `REDIS_URL` | _(unset)_ | Persistent stats + page cache; falls back to in-memory |
| `L2AGENT_API_KEY` | _(unset)_ | If set, requests must send `X-API-Key` header |

## Security

- **SSRF protection:** only `http(s)` URLs; private, loopback, link-local and cloud-metadata addresses are blocked at dial time (resistant to DNS rebinding).
- **Response cap:** at most 5 MB read from any upstream.
- **Rate limiting:** 60 requests/min per client IP.
- **API keys** are accepted via header only, never query parameters.

## Architecture

```
cmd/l2agent          single binary: `serve` (HTTP) and `gateway` (MCP stdio)
internal/analyzer    pure HTML → structured JSON extraction + token accounting
internal/fetch       SSRF-hardened outbound HTTP client
internal/server      HTTP API, middleware (CORS, auth, rate limit), caching
internal/mcp         MCP stdio gateway
internal/store       Redis (or in-memory) stats + page cache
dashboard/           static dashboard (deployable to Vercel)
```

## Deployment

- **Railway:** uses the included `Dockerfile` and `railway.toml` (health check on `/healthz`). Add a Redis service and set `REDIS_URL` to its connection string for persistent stats.
- **Vercel:** serves `dashboard/index.html` as a static site. Open it and point it at your Railway API URL.

## Development

```bash
make test    # unit tests
make vet     # static analysis
make build   # binary in ./bin
make docker  # container image
```

---

**Built for agents, not humans.**
