# L2Agent – Agent OS (Optimism Layer for AI Agents)

**Built for agents, not humans. Eliminate token waste on HTML/legacy web.**

Convert messy web pages into clean, structured JSON + actions. The proxy reduces token usage by stripping HTML/CSS/JS noise and returning only the essential data.

## ⚡ Why

- Agents waste **5–10x tokens** parsing HTML, navigating UIs, and handling authentication.
- L2Agent extracts just what an agent needs: forms, data, clickable elements.
- **Real example**: scraping a product page → **45 tokens** instead of 400+.

## 🚀 Quick Start

```bash
# Install
go install github.com/Emodv/l2agent/cmd/l2agent@latest

# Start the gateway (JSON‑RPC API)
l2agent gateway

# Start the HTTP proxy (listens on :8080)
l2agent proxy
```

🧪 Use It

Send a URL to the proxy and get structured JSON:

```bash
curl -X POST http://localhost:8080/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/form"}'
```

🧩 Components

· Web Analyzer – extracts forms and clickable elements from any URL.
· Proxy – token‑saving engine; speaks JSON‑RPC and HTTP.
· Skill Registry – plug in custom tools dynamically.
· Gateway – central API endpoint for agent requests.
· Audit Logging – logs all agent actions with timestamps.

🛠️ Tech Stack

· Go 1.21+ (91.2% of the codebase)
· goquery v1.9.3 – HTML parsing
· go‑redis v8.11.5 – caching
· Docker + Fly.io ready

📊 Status

Active development – latest commit: June 9, 2026.
Benchmarks, PyPI package, and more examples coming soon.

---

Built for agents, by agents.

```
