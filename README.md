# L2Agent — Structured Web Access for AI Agents

**Built for agents, not humans. Stop burning tokens on HTML noise.**

L2Agent fetches web pages and returns only what an agent needs — forms, fields, buttons, links — as compact JSON. Token savings are **measured per request** (raw HTML size vs. JSON output size) and reported honestly in every response.

**Live API:** `https://l2agent-production.up.railway.app`

## Try It Now (No Setup)

```bash
# Health check
curl https://l2agent-production.up.railway.app/healthz

# Analyze any URL
curl "https://l2agent-production.up.railway.app/v1/analyze?url=https://github.com/Emodv/l2agent&agent_id=my-agent"

# Parse raw HTML you already have
curl -X POST "https://l2agent-production.up.railway.app/v1/analyze?agent_id=my-agent" \
  --data-binary '<html><body><form action="/signup" method="POST"><input name="email" type="email" required/><button type="submit">Sign Up</button></form></body></html>'

# Check your token savings
curl "https://l2agent-production.up.railway.app/v1/stats?agent_id=my-agent"
```

## Quick Start (Self-Hosted)

```bash
git clone https://github.com/Emodv/l2agent && cd l2agent
make build

# HTTP API on :8080
./bin/l2agent serve

# MCP gateway over stdio (Claude Desktop / Cursor / Cline)
./bin/l2agent gateway
```

No configuration required. `REDIS_URL` is optional for persistent stats.

## HTTP API

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/healthz` | Liveness probe |
| `GET` | `/v1/analyze?url=...` | Fetch a URL and return structured JSON |
| `POST` | `/v1/analyze` | Parse raw HTML body (no outbound fetch) |
| `POST` | `/v1/submit` | Submit form fields to a URL |
| `GET` | `/v1/stats[?agent_id=]` | Measured token usage and savings |

Example `/v1/analyze` response:

```json
{
  "url": "https://example.com/signup",
  "title": "Sign Up - Acme SaaS",
  "forms": [
    {
      "action": "https://example.com/api/register",
      "method": "POST",
      "fields": [
        {"name": "email",    "type": "email",    "required": true},
        {"name": "password", "type": "password", "required": true},
        {"name": "plan",     "type": "select"}
      ]
    }
  ],
  "links":   [{"text": "Login", "href": "https://example.com/login"}],
  "buttons": [{"text": "Create Account", "type": "submit"}],
  "meta": {
    "raw_tokens_est":       1575,
    "optimized_tokens_est": 370,
    "tokens_saved_est":     1205,
    "savings_pct":          76.5,
    "note": "estimates use ~4 chars/token; raw = original HTML, optimized = this JSON"
  }
}
```

## MCP Gateway

`l2agent gateway` speaks the Model Context Protocol over stdio:

| Tool | What it does |
|------|--------------|
| `analyze_url` | Fetches and parses a page, returns structured JSON |
| `submit_form` | Submits form-encoded fields to a URL |
| `get_agent_stats` | Returns measured token usage and savings |

**Claude Desktop** (`~/.claude/claude_desktop_config.json`):
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
| `L2AGENT_API_KEY` | _(unset)_ | If set, requests must include `X-API-Key` header |

## Security

- **SSRF protection:** only `http(s)` to public IPs; private, loopback, and cloud-metadata addresses blocked at dial time (DNS-rebinding resistant).
- **Response cap:** at most 5 MB read from any upstream.
- **Rate limiting:** 60 requests/min per client IP.
- **API keys** via header only, never query parameters.

## Architecture

```
cmd/l2agent          single binary: `serve` (HTTP) or `gateway` (MCP stdio)
internal/analyzer    HTML → structured JSON + measured token accounting
internal/fetch       SSRF-hardened outbound HTTP client
internal/server      HTTP API, CORS, auth, rate limiting, 10-min page cache
internal/mcp         MCP stdio gateway
internal/store       Redis or in-memory stats + cache
dashboard/           static stats dashboard
openapi.yaml         full OpenAPI 3.1 spec
llms.txt             machine-readable summary for AI agent discovery
AGENTS.md            AI agent integration guide
```

## Deployment

- **Railway:** `Dockerfile` + `railway.toml` included. Health check on `/healthz`. Add a Redis service and set `REDIS_URL` for persistent stats.
- **Vercel:** `vercel.json` included — serves `dashboard/index.html` as a static site.

## Development

```bash
make test    # unit tests
make vet     # static analysis
make build   # binary → ./bin/l2agent
make docker  # container image
```

---

**Built for agents, not humans.** | [OpenAPI Spec](openapi.yaml) | [Agent Guide](AGENTS.md) | [llms.txt](llms.txt)
