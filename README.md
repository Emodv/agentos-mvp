# L2Agent – Agent OS (Optimism Layer for AI Agents)

**Built for agents, not humans. Eliminate token waste on HTML/legacy web.**

Convert messy web pages into clean, structured JSON + actions. The proxy reduces token usage by stripping HTML/CSS/JS noise and returns only the essential data AI agents actually need.

## ⚡ Why

- Agents waste **5–10× more tokens** parsing HTML, CSS, JavaScript, and navigating websites.
- L2Agent extracts only what matters: forms, buttons, links, structured data, and actions.
- Reduces context size before it reaches the LLM.
- Makes AI-to-AI communication faster, cheaper, and more reliable.
- **Real example:** a product page that normally requires 400+ tokens can often be represented in around **45 tokens**.

## 🚀 Quick Start

```bash
# Install
go install github.com/Emodv/l2agent/cmd/l2agent@latest

# Start the gateway (JSON-RPC API)
l2agent gateway

# Start the HTTP proxy
l2agent proxy
```

## 🧪 Example

Send a URL to the proxy and receive structured JSON instead of raw HTML.

```bash
curl -X POST http://localhost:8080/scrape \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/form"}'
```

Example response:

```json
{
  "title": "Contact Form",
  "forms": [
    {
      "action": "/submit",
      "method": "POST"
    }
  ],
  "buttons": [
    "Submit"
  ]
}
```

## 🧩 Components

- **Web Analyzer** – extracts forms, links, inputs, buttons, and page structure.
- **HTTP Proxy** – converts noisy web pages into compact machine-readable JSON.
- **Gateway** – JSON-RPC endpoint for AI agents.
- **Skill Registry** – dynamically loads and manages agent capabilities.
- **Audit Logger** – records agent activity and execution history.
- **Caching Layer** – reduces repeated processing and latency.

## 🛠 Tech Stack

- Go 1.21+
- goquery
- go-redis
- JSON-RPC
- HTTP API
- Docker-ready architecture

## 📈 What Problem Does It Solve?

Today's web is optimized for humans.

AI agents must download and parse enormous amounts of HTML, CSS, JavaScript, advertisements, menus, navigation bars, and layout code just to locate a single button or form.

L2Agent acts like an **L2 scaling layer for AI**, transforming bloated websites into compact structured representations that are easier and cheaper for language models to consume.

The result:

- Lower token costs
- Faster execution
- Smaller context windows
- Better reliability
- Easier agent automation

## 🎯 Vision

The future is not humans browsing websites.

The future is AI agents communicating directly with services through structured interfaces.

L2Agent provides the optimization layer that bridges today's human web with tomorrow's agent-first internet.

## 📊 Status

- Active development
- Open source
- Benchmarks in progress
- Additional integrations and SDKs planned

---

**Built for agents, not humans.**
