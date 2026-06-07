# Agent OS MVP

**Co-Founder & Author: [Emodv](https://github.com/Emodv)**

Universal platform for AI agents: MCP gateway + HTML proxy.

## Quick start

```bash
make build
./bin/proxy &
./bin/gateway
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | ./bin/gateway
