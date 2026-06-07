#!/bin/bash
# Agent OS Test Script - Simulate multiple agent calls
# Co-Founder & Author: Emodv

echo "=== Testing Agent OS Gateway ==="
echo ""

echo "1. List available tools:"
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | ./bin/gateway
echo ""

echo "2. Call web_analyze as agent_001:"
echo '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"web_analyze","agent_id":"agent_001","arguments":{"url":"https://httpbin.org/forms/post"}}}' | ./bin/gateway
echo ""

echo "3. Call web_analyze as agent_002 (different agent, separate tracking):"
echo '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"web_analyze","agent_id":"agent_002","arguments":{"url":"https://example.com"}}}' | ./bin/gateway
echo ""

echo "4. Anonymous call (no agent_id):"
echo '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"web_analyze","arguments":{"url":"https://example.com"}}}' | ./bin/gateway
echo ""

echo "5. Test rate limiting (60 rapid calls would trigger warning)"
echo "--- Test Complete ---"
