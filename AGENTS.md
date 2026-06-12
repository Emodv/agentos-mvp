# L2Agent – Agent Integration Guide

## What is L2Agent?

A structured-web-access layer for AI agents. Instead of parsing raw
HTML, agents get compact JSON describing a page's forms, fields,
buttons and links. Token savings are **measured per request** (raw HTML
size vs. JSON output, ~4 chars/token estimate) and included in every
response under `meta` — no hardcoded marketing numbers.

## Quick Start

```bash
make build

# HTTP API on :8080 (or $PORT)
./bin/l2agent serve

# MCP gateway over stdio
./bin/l2agent gateway
```

## MCP Tools

### 1. analyze_url
Fetches and parses the page in-process; returns structured JSON.

```json
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"analyze_url","arguments":{"url":"https://httpbin.org/forms/post","agent_id":"my-agent-001"}}}
```

### 2. submit_form
Submits form-encoded fields and returns the result status.

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"submit_form","arguments":{"url":"https://httpbin.org/post","fields":{"name":"John Doe","email":"john@example.com"},"agent_id":"my-agent-001"}}}
```

### 3. get_agent_stats
Returns measured usage and savings for an agent.

```json
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_agent_stats","arguments":{"agent_id":"my-agent-001"}}}
```

## HTTP Endpoints

```
GET  /healthz
GET  /v1/analyze?url=YOUR_URL        (identify with X-Agent-ID header)
POST /v1/submit                      {"url":..., "fields":{...}, "agent_id":...}
GET  /v1/stats[?agent_id=...]
POST /scrape                         legacy alias for analyze
```

## Auth & Limits

- Set `L2AGENT_API_KEY` to require the `X-API-Key` header. No key = open dev mode.
- 60 requests/min per client IP.
- Only public `http(s)` destinations are fetched (SSRF guard); responses capped at 5 MB.

## Test

```bash
./test_agent.sh
```
