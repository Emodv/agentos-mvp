# KO (Knowledge Object) Specification v1

## Where It Fits

```
┌─────────────────────────────────────────────────┐
│  Applications / Agents                           │
├─────────────────────────────────────────────────┤
│  Frameworks (LangChain, AutoGPT, DSPy)           │
├─────────────────────────────────────────────────┤
│  ██████████████████████████████████████████████ │
│  █  IntelGit – KO Protocol & Registry         █ │
│  █  (versioned, verifiable reasoning)          █ │
│  ██████████████████████████████████████████████ │
├─────────────────────────────────────────────────┤
│  Model Providers (OpenAI, Anthropic, Llama)      │
├─────────────────────────────────────────────────┤
│  Infrastructure (compute, storage, network)      │
└─────────────────────────────────────────────────┘
```

IntelGit is not a model, not a framework, not a vector DB.
It is the **coordination plane** that makes agents cheaper, faster, and trustworthy.

---

## Identifier

`ko://sha256/<hex>` where `<hex>` = SHA-256 of the canonical JSON representation
(all fields except `id`, but including `proof.signature`).

---

## Schema (JSON-LD compatible)

```json
{
  "@context": "https://intelgit.ai/ko-v1",
  "id": "ko://sha256/...",
  "goal": "Find top 3 competitors for a vegan bakery in Berlin",
  "inputs": {
    "location": "Berlin",
    "niche": "vegan bakery"
  },
  "output_hash": "sha3-256:b7c5a...",
  "proof": {
    "model": "gpt-4-turbo",
    "execution_trace_hash": "sha256:...",
    "signature": "ed25519:...",
    "signer_did": "did:key:z6Mks..."
  },
  "dependencies": [],
  "confidence": 0.93,
  "cost_usd": 0.012,
  "latency_ms": 3400,
  "license": "MIT | reuse-with-attribution | commercial",
  "created_at": "ISO8601"
}
```

---

## Storage

- **Content-addressed**: `ko://` ID is SHA-256 of canonical JSON (excl. `id`).
- **Local index**: SQLite in `~/.intelgit/index.db` with goal embeddings.
- **Output cache**: Raw output bytes in `~/.intelgit/outputs/`.
- **IPFS** (optional): Output pinned to IPFS CID when daemon is available.
- **Global registry** (roadmap): IntelGit Hub — like GitHub for KOs.

---

## Protocol Flow

### Write path (agent commits new intelligence)

```
Agent has a task
      │
      ▼
Execute on LLM
      │
      ▼
Capture evidence (prompt, output, cost, latency, model)
      │
      ▼
Sign with agent's DID:key private key (Ed25519)
      │
      ▼
Store KO locally (SQLite index + output cache + IPFS)
      │
      ▼
[Optional] push to global registry
```

### Read path (agent reuses existing intelligence)

```
Agent needs to solve goal G
      │
      ▼
Query local store (semantic similarity on goal embeddings)
      │
   Found?
   ╱     ╲
 Yes      No
  │        │
  │        ▼
  │  Query global registry (semantic search)
  │        │
  │     Found?
  │     ╱    ╲
  │   Yes     No
  │    │       │
  │    │       ▼
  │    │  Fall back to fresh LLM call → commit as new KO
  │    │
  └────┤
       ▼
  Verify signature & ID integrity
       │
       ▼
  Return cached output
  Pay micropayment to creator
```

---

## Verification

1. Recompute `output_hash` from stored output (SHA3-256).
2. Recompute `id` from canonical JSON (SHA-256 of all fields except `id`).
3. Check Ed25519 signature against `signer_did`.
4. Optionally re-run execution trace (if available).

---

## Canonical JSON Rules

- All fields except `id` included.
- Proof field included (with `signature`).
- **Signed payload**: canonical JSON excluding both `id` and `proof.signature`.
- Keys sorted alphabetically, no extra whitespace.
- `created_at` serialised as ISO 8601 string.

---

## Feature Matrix

| Feature | Description | Status |
|---|---|---|
| Content-addressed IDs | `ko://sha256/…` | ✅ |
| Ed25519 signing via DID:key | Cryptographic provenance | ✅ |
| SQLite local store | Fast local index | ✅ |
| Output cache | `~/.intelgit/outputs/` | ✅ |
| IPFS pinning | Decentralised storage | ✅ (optional) |
| Semantic deduplication | Embedding-based goal similarity | ✅ |
| DAG dependencies | KOs reference parent KOs | ✅ (schema) |
| `ko find` | Similarity search CLI | ✅ |
| `ko reuse` | Reuse without LLM call | ✅ |
| LangChain `KOAgent` | Transparent caching wrapper | ✅ |
| Micropayments | Reuse fees to creators | 🔜 |
| Global registry | IntelGit Hub | 🔜 |
| Agent DNA | Portable DID + memory + prefs | 🔜 |
| CI/CD for intelligence | Auto-verify with multiple models | 🔜 |
| DSPy / AutoGPT integrations | Framework adapters | 🔜 |
