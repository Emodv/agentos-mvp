#!/bin/bash
# L2Agent smoke test — exercises the MCP gateway and the HTTP API.
set -e

make build

echo "=== MCP gateway (stdio) ==="
echo ""

echo "1. initialize + tools/list:"
printf '%s\n%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | ./bin/l2agent gateway
echo ""

echo "2. analyze_url as agent_001:"
echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"analyze_url","arguments":{"url":"https://httpbin.org/forms/post","agent_id":"agent_001"}}}' | ./bin/l2agent gateway
echo ""

echo "3. get_agent_stats:"
echo '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"get_agent_stats","arguments":{"agent_id":"agent_001"}}}' | ./bin/l2agent gateway
echo ""

echo "=== HTTP API ==="
echo "Start the server with 'make run', then:"
echo '  curl "http://localhost:8080/healthz"'
echo '  curl -H "X-Agent-ID: agent_001" "http://localhost:8080/v1/analyze?url=https://example.com"'
echo '  curl "http://localhost:8080/v1/stats"'
echo ""
echo "--- Test complete ---"
