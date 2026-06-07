# Agent OS MVP

**Co-Founder & Author: [Emodv](https://github.com/Emodv)**

Universal platform for AI agents: MCP gateway + HTML proxy with **agent tracking, rate limiting, token budgeting, and audit logging**.

## Features

- **MCP Gateway** - JSON-RPC over stdin, skill discovery and execution
- **HTML-to-API Proxy** - Turn any website into structured API endpoints
- **Agent ID Tracking** - Every call is attributed to a specific agent
- **Rate Limiting** - 60 requests/minute per agent (prevents abuse)
- **Token Budgeting** - Track usage per agent (1 token ≈ 4 chars of output)
- **Audit Logging** - Complete action history for debugging and billing
- **Daily Token Reset** - Automatic reset after 24 hours

## Quick Start

```bash
# Clone and build
git clone https://github.com/Emodv/agentos-mvp
cd agentos-mvp
make build

# Terminal 1: Start the proxy
./bin/proxy

# Terminal 2: Start the gateway
./bin/gateway
