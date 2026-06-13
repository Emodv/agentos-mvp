# KO (Knowledge Object) Specification v1

## Identifier
`ko://sha256/<hex>` where `<hex>` = SHA256 of canonical JSON representation.

## Schema (JSON-LD compatible)
```json
{
  "@context": "https://intelgit.ai/ko-v1",
  "id": "ko://sha256/...",
  "goal": "string (human readable)",
  "inputs": { ... },
  "output_hash": "sha3(...)",
  "proof": {
    "model": "string",
    "execution_trace_hash": "sha256(...)",
    "signature": "ed25519(...)",
    "signer_did": "did:key:z6M..."
  },
  "dependencies": ["ko://..."],
  "confidence": 0.0-1.0,
  "cost_usd": 0.0,
  "latency_ms": 0,
  "license": "MIT | reuse-with-attribution | commercial",
  "created_at": "ISO8601"
}
```

## Storage
- Content-addressed: `ko://` ID maps to IPFS CID (optional).
- Local index: SQLite with full-text search.

## Verification
1. Recompute `output_hash` from output.
2. Check signature against `signer_did`.
3. Optionally re-run execution trace (if available).

## ID Computation
The canonical ID is computed by:
1. Serializing the KO fields (excluding `id`) to canonical JSON (sorted keys, no extra whitespace).
2. SHA256-hashing the UTF-8 bytes.
3. Prefixing with `ko://sha256/`.
