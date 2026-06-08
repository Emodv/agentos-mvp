# L2Agent – Agent Integration Guide

## What is L2Agent?

The agent-native API layer. Instead of burning 400+ tokens parsing
human-designed web interfaces, agents get clean JSON endpoints.

**Before:** 400 tokens per action
**After:** 45 tokens per action
**Savings: 89%**

## Quick Start for Agents

Start the Gateway:
./bin/gateway

Start the Proxy:
./bin/proxy
Runs on :8080

## Available Tools

### 1. analyze_url
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"analyze_url","arguments":{"url":"https://example.com/intake","agent_id":"my-agent-001"}}}

### 2. submit_form
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"submit_form","arguments":{"url":"https://example.com/submit","fields":{"name":"John Doe","email":"john@example.com"},"agent_id":"my-agent-001"}}}

### 3. get_agent_stats
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_agent_stats","arguments":{"agent_id":"my-agent-001"}}}

## HTTP Endpoints

GET  /health
GET  /v1/analyze?url=YOUR_URL
POST /v1/submit

## Auth
Set: L2AGENT_API_KEY=your-key
Header: X-API-Key: your-key
No key = dev mode

## Test

echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | ./bin/gateway
curl "http://localhost:8080/health"
curl "http://localhost:8080/v1/analyze?url=https://httpbin.org/forms/post"

Author: Emodv – https://github.com/Emodv
