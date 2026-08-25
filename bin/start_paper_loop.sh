#!/bin/bash
# Starts the paper-lane runner daemon (idempotent). Called by
# alpaca_key_watch.sh the moment real Alpaca paper keys land in .env.
#
# Safety: ALPACA_IS_LIVE=1 selects the MCP lane, whose server subprocess is
# hard-forced to ALPACA_PAPER=true inside client.py — this daemon CANNOT
# reach a real-money account. config.validate_paper_config() additionally
# refuses any explicit ALPACA_REAL_TRADING=1.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

export PATH="$HOME/.local/bin:$PATH"   # uvx for the MCP server subprocess

if [ ! -f "$REPO_ROOT/.env" ]; then
  echo "start_paper_loop: no .env — nothing to do" >&2
  exit 0
fi
set -a; . "$REPO_ROOT/.env"; set +a   # ALPACA_API_KEY / ALPACA_SECRET_KEY

if [ -z "${ALPACA_API_KEY:-}" ] || [ -z "${ALPACA_SECRET_KEY:-}" ]; then
  echo "start_paper_loop: .env missing keys — nothing to do" >&2
  exit 0
fi

mkdir -p "$REPO_ROOT/state/paper"
PIDFILE="$REPO_ROOT/state/paper/paper_loop.pid"
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "start_paper_loop: already running (pid $(cat "$PIDFILE"))"
  exit 0
fi

cd "$REPO_ROOT/options"
nohup env ALPACA_IS_LIVE=1 "$REPO_ROOT/cryptobot/.venv/bin/python" \
  -m options.runner --interval 300 \
  >> "$REPO_ROOT/state/paper/paper_loop.log" 2>&1 &
echo $! > "$PIDFILE"
echo "start_paper_loop: paper loop started (pid $!)"
