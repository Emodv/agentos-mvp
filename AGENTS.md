
# Agent OS – for AI agents

## Build
```bash
make build
```

Run gateway

```bash
./bin/gateway
```

Accepts JSON‑RPC 2.0 over stdin.

Run proxy

```bash
./bin/proxy
```

Listens on :8080. Endpoints:

· GET /v1/analyze?url=<url> – extract forms/clickables
· POST /v1/submit – submit a form

Test

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | ./bin/gateway
curl "http://localhost:8080/v1/analyze?url=https://httpbin.org/forms/post"
```

```

