# IntelGit – Git for Intelligence

> Version-controlled, cryptographically verifiable, reusable AI reasoning.

```bash
ko commit "analyze Q3 sales"      →  ko://sha256/abc123…
ko checkout ko://sha256/abc123…   →  retrieve the analysis
ko verify ko://sha256/abc123…     →  cryptographic proof
ko push                           →  share to global registry
ko install market-analysis/tech   →  like npm for intelligence
```

---

## The Problem

Every AI agent starts from zero.

- An agent spends $0.10 and 5 seconds figuring out "what is the capital of France?"
- Another agent, one minute later, spends the same $0.10 and 5 seconds.
- A brilliant Kubernetes debugging chain is generated and then lost in a chat log.
- You cannot verify that an AI output came from the claimed model, prompt, or reasoning path.
- An agent built on OpenAI cannot reuse memory or reasoning on Anthropic or a local model.

**Result:** Trillions of dollars of redundant compute. No trust without central authority. No economic incentive to share intelligence.

---

## The Solution: Knowledge Objects (`ko://`)

A Knowledge Object is a signed, content-addressed receipt of an AI reasoning step:

```json
{
  "id": "ko://sha256/abc123…",
  "goal": "analyze Q3 sales trends",
  "inputs": { "dataset": "s3://sales/q3.csv" },
  "output_hash": "sha3-256:def456…",
  "proof": {
    "model": "gpt-4-turbo",
    "execution_trace_hash": "sha256:…",
    "signature": "ed25519:…",
    "signer_did": "did:key:z6M…"
  },
  "dependencies": ["ko://sha256/…"],
  "confidence": 0.93,
  "cost_usd": 0.012,
  "latency_ms": 1840,
  "license": "reuse-with-attribution",
  "created_at": "2024-06-01T12:00:00Z"
}
```

Every insight becomes a **reusable, monetisable, auditable asset**.

---

## Install

```bash
pip install intelgit
# or from source
git clone https://github.com/intelgit/ko
cd ko && pip install -e .
```

---

## Quick Start

```bash
export OPENAI_API_KEY=sk-…

# Commit a reasoning step (runs the LLM, captures proof)
ko commit --goal "What is the capital of France?" --inputs '{}'
# → Committed: ko://sha256/72ea86c…

# Retrieve metadata
ko checkout ko://sha256/72ea86c…

# Cryptographically verify
ko verify ko://sha256/72ea86c…
# PASS  ID integrity
# PASS  Signature (did:key:z6M…)

# Search past knowledge
ko search "capital"
ko log --limit 20

# Publish to IPFS (requires ipfs daemon)
ko push ko://sha256/72ea86c…
```

---

## CLI Reference

| Command | Description |
|---|---|
| `ko commit` | Run an LLM goal, capture execution proof, store KO |
| `ko checkout <id>` | Retrieve KO metadata; `--json-out` for full JSON |
| `ko verify <id>` | Cryptographic integrity + signature check |
| `ko push <id>` | Publish to IPFS |
| `ko log` | List recent KOs |
| `ko search <query>` | Full-text search by goal |
| `ko install <pkg>` | Install a knowledge package *(roadmap)* |

---

## Why Every AI Agent Needs This

**For agent developers**
- Cut token costs 80–95% by reusing existing KOs instead of recomputing
- Ship faster – assemble workflows from pre-verified intelligence modules
- Every decision is cryptographically signed and versioned

**For agent operators**
- Trust delegation – use a specialist agent's output without re-running it
- Portable agents – DID-based identity moves across OpenAI, Anthropic, local models
- Failure recovery – checkpointed KOs let you restart from last success

**For the ecosystem**
- Economic flywheel: agents earn passive income when others reuse their KOs
- Decentralised trust – no single company controls verification

**Concrete example:** A medical diagnosis agent needs drug interaction data. Instead of calling GPT-5 every time, it queries the IntelGit registry, finds a verified KO signed by a licensed pharmacist, and reuses it for $0.001 and 10 ms — with full cryptographic proof.

---

## Architecture

```
ko commit
    │
    ▼
┌─────────────────────────────────────────────────┐
│  Local DAG Store  (SQLite index + IPFS content) │
└────────────────────┬────────────────────────────┘
                     │  ko push
                     ▼
           Public Registry (GitHub for KOs)
                     │
                     ▼
         Decentralised Verifier Network
```

- **Content-addressed** – `ko://sha256/<hex>` is the SHA-256 of the canonical KO JSON
- **Ed25519 signatures** via `did:key` – no CA, no trust anchor, portable
- **Local-first** – SQLite index in `~/.intelgit/`, IPFS optional
- **Dependency graph** – KOs can reference parent KOs, forming a verifiable reasoning DAG

---

## Running Tests

```bash
pip install -e ".[dev]"
pytest
```

14 tests cover the KO model, Ed25519 crypto, and local store.

---

## Roadmap

- [x] KO schema & local SQLite store
- [x] Commit, checkout, verify CLI
- [x] Ed25519 signing via DID:key
- [ ] Semantic hashing (fuzzy deduplication)
- [ ] Agent DNA (portable identity + preferences)
- [ ] Global registry (like GitHub for KOs)
- [ ] `ko install` – dependency management
- [ ] Micropayment layer (reuse fees)
- [ ] LangChain / AutoGPT / DSPy integrations

---

## The Bigger Picture

We have Git for code. Docker for software. Stripe for payments. Cloudflare for distribution.

**We have nothing for the output of AI agents** – which will soon be the world's most valuable production resource.

IntelGit is the missing layer of the AI stack.

```
More agents → more KOs → higher reuse → lower costs → more adoption → more agents
```

---

## License

MIT
