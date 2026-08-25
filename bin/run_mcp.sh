#!/usr/bin/env bash
# Alpaca MCP server launcher for hackathon (paper trading).
# Usage: ./bin/run_mcp.sh [stdio|streamable-http|sse]
# Requires ~/cryptobot-train/.env with ALPACA_API_KEY / ALPACA_SECRET_KEY (paper).
set -euo pipefail
cd "$(dirname "$0")/.."
TRANSPORT="${1:-stdio}"
if [ ! -f .env ]; then
  echo 'ERROR: .env missing - copy .env.example and fill ALPACA_API_KEY/ALPACA_SECRET_KEY (paper).' >&2
  exit 1
fi
PORT="${MCP_PORT:-8765}"
case "$TRANSPORT" in
  stdio)
    exec uvx alpaca-mcp-server --transport stdio --env-file .env
    ;;
  streamable-http|sse)
    exec uvx alpaca-mcp-server --transport "$TRANSPORT" --host 0.0.0.0 --port "$PORT" --env-file .env
    ;;
  *)
    echo "unknown transport: $TRANSPORT" >&2
    exit 2
    ;;
esac
