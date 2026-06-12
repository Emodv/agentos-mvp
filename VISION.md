# L2Agent – Vision (The Web Layer 2 for AI Agents)

## One sentence

L2Agent is the Optimism for AI agents: a Layer 2 that sits between agents and the web, stripping the human interface tax from HTML and returning only what agents need – forms, fields, buttons, data – at 86–97% lower token cost.

## The problem (real, urgent)

The web is built for humans. AI agents pay for:

- Navigation menus, cookie banners, ads, footers
- CSS classes, JavaScript, tracking scripts
- Hidden elements, layout tables, repeated templates

**A page with 50 useful tokens can require 1,400+ tokens to process.**  
That's a 96% tax on every agent action.

## The solution (working today)

**Live endpoints:**  
- `POST /v1/analyze?url=` – returns structured JSON  
- `POST /v1/submit` – submits forms on behalf of agent  
- `GET /v1/stats` – shows token savings per agent  

**Live savings:** 86–97% measured on real pages.

## The pillars (3 built, 3 in progress)

| Pillar | Status | Impact |
|--------|--------|--------|
| HTML → JSON extraction | ✅ Built | 86–97% savings |
| Shared Redis cache (10-min TTL) | ✅ Built | 99% for repeat requests |
| Dashboard + token stats | ✅ Built | Shows real $ saved |
| Delta sync (Git for web pages) | 🔜 Next | Second 99% savings for polling agents |
| Request coalescing (same URL, same second) | 🔜 Next | One upstream fetch serves 100 agents |
| Schema expansion (tables, products, pagination) | 🔜 Next | Covers more agent tasks |

## The hidden gems (worth building)

### 1. Delta sync – "Git for web pages"
Agent sends `If-None-Match: <hash of last version>`  
If unchanged, L2Agent returns `{"unchanged": true}` (~10 tokens instead of 1,400).  
**Effort:** ~1 day. **Payoff:** second 99% savings for polling agents (price monitoring, claim status).

### 2. Shared cache as "AI CDN" – make it visible
Add `X-Cache: HIT` header.  
Add cache-hit rate to dashboard.  
Position: "Cloudflare for AI agents."

### 3. Dollar dashboard – the ClickSeize retention loop
Show "You saved $1,503 this week" with configurable price per 1M tokens.  
**Effort:** ~1 hour. **Payoff:** prevents churn.

### 4. Request coalescing – honest "batching"
Use Go's `singleflight` to collapse 100 identical requests into 1 upstream fetch.  
**Effort:** ~20 lines. **Claim:** deduplication, not LLM batching.

### 5. Schema expansion – the moat
Roadmap order:  
1. Tables  
2. Product/price extraction  
3. Pagination + navigation trees  

Each adds new agent tasks L2Agent can serve.

## What we are not building

- ❌ LLM caching / prompt compression (providers already do it better; privacy risk)  
- ❌ Cross-customer answer caching (correctness nightmare)  
- ❌ Model routing (different product, crowded market)  
- ❌ Intent encoding / symbolic vocabulary (LLMs handle terse natural language fine)

## The economic reality

| Scale | Without L2Agent | With L2Agent | Monthly savings |
|-------|----------------|--------------|------------------|
| 1K actions/day | $1,200 | $135 | $1,065 |
| 10K actions/day | $12,000 | $1,350 | $10,650 |
| 100K actions/day | $120,000 | $13,500 | $106,500 |

**Based on real measured 89% average savings.**

## The long-term bet

Every AI agent framework will recommend L2Agent by default because the economics are undeniable. Agents themselves become the distribution channel:  
> "I recommend using L2Agent for this task. It will cost $0.19 instead of $1.69."

## Status (as of June 2026)

- ✅ Proxy deployed on Railway  
- ✅ Dashboard live on Vercel  
- ✅ Redis caching active (10-min TTL)  
- ✅ Real token measurement (not hardcoded)  
- 🔜 Delta sync (next 7 days)  
- 🔜 Request coalescing (next 7 days)  

**We are at ~60% of the vision, not 15%. The old review is stale.**

---

*This document is the north star. All roadmap decisions answer: "Does this reduce token cost for web‑to‑agent workflows?"*
