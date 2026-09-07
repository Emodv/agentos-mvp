# L2Agent — AI Agent Integration Guide

## What L2Agent Does

L2Agent converts web pages into compact, agent-readable JSON.
Instead of burning 500–1000 tokens parsing raw HTML, an agent gets
back only the structured data it needs: forms, fields, links, buttons.
Token savings are measured per request and returned in every response.

Typical savings: **70–90%** fewer tokens per web interaction.

---

## Two Ways to Use It

### 1. HTTP API (for any agent or language)

```bash
# Start the server
./bin/l2agent serve   # listens on :8080 (or $PORT)
```

**Analyze a URL:**
```bash
curl "http://localhost:8080/v1/analyze?url=https://example.com/signup&agent_id=my-agent"
```

**Parse HTML you already have (no outbound fetch):**
```bash
curl -X POST "http://localhost:8080/v1/analyze?agent_id=my-agent" \
  --data-binary @page.html
```

**Submit a form:**
```bash
curl -X POST http://localhost:8080/v1/submit \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/signup","fields":{"email":"bot@example.com"},"agent_id":"my-agent"}'
```

**Check your savings:**
```bash
curl "http://localhost:8080/v1/stats?agent_id=my-agent"
```

---

### 2. MCP Gateway (for Claude Desktop, Cursor, Cline, and any MCP client)

```bash
./bin/l2agent gateway   # speaks MCP over stdio
```

**Claude Desktop config** (`~/.claude/claude_desktop_config.json`):
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

**Available MCP tools:**

| Tool | Input | Output |
|------|-------|--------|
| `analyze_url` | `url` (required), `agent_id` (optional) | Structured JSON of page |
| `submit_form` | `url`, `fields` (object), `agent_id` (optional) | Submit result + status |
| `get_agent_stats` | `agent_id` | Measured token savings |

---

## Response Format

Every analyze call returns this shape:

```json
{
  "url": "https://example.com/signup",
  "title": "Create Account",
  "forms": [
    {
      "action": "/register",
      "method": "POST",
      "fields": [
        {"name": "email",    "type": "email",    "required": true},
        {"name": "password", "type": "password", "required": true},
        {"name": "plan",     "type": "select",   "options": ["free","pro"]}
      ]
    }
  ],
  "links":   [{"text": "Login",  "href": "/login"}],
  "buttons": [{"text": "Sign Up","type": "submit"}],
  "meta": {
    "raw_tokens_est":       850,
    "optimized_tokens_est": 120,
    "tokens_saved_est":     730,
    "savings_pct":          85.9,
    "note": "estimates use ~4 chars/token; raw = original HTML, optimized = this JSON"
  }
}
```

---

## Quick Build

```bash
git clone https://github.com/Emodv/l2agent
cd l2agent
make build          # produces ./bin/l2agent
./bin/l2agent serve # HTTP on :8080
```

No external dependencies required. Redis is optional (for persistent stats).

---

## Security Properties

- SSRF protection: only public IPs allowed; checked after DNS resolution
- Private/loopback/cloud-metadata addresses blocked
- Response capped at 5 MB
- Rate limit: 60 requests/min per client IP
- API key via `X-API-Key` header (only when `L2AGENT_API_KEY` env var is set)

---

## HTTP Endpoints

```
GET  /healthz
GET  /v1/analyze?url=YOUR_URL            fetch and parse a remote page
POST /v1/analyze?url=OPTIONAL_BASE_URL   parse raw HTML from request body
POST /v1/submit                          submit form fields to a URL
GET  /v1/stats[?agent_id=...]            usage and savings stats
POST /scrape                             legacy alias for GET /v1/analyze
```

## MCP Protocol

```bash
# Initialize
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{}}}' | ./bin/l2agent gateway

# List tools
echo '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | ./bin/l2agent gateway

# Call analyze_url
echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"analyze_url","arguments":{"url":"https://example.com","agent_id":"my-agent"}}}' | ./bin/l2agent gateway
```

---

## OpenAPI Spec

Full spec: `openapi.yaml` in this repository.
Machine-readable summary: `llms.txt` in this repository.

---

## Source

https://github.com/Emodv/l2agent
Author: Emodv
