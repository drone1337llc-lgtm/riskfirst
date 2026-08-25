#!/bin/bash
# Runs the full RiskFirst guardrail suite with the CANONICAL venv.
# Usage: bin/run_tests.sh
# Canonical interpreter is cryptobot/.venv (the same one start_paper_loop.sh
# uses for the live paper lane) — do NOT run this suite from v9-venv or any
# other venv; alpaca-py==0.43.5 is required at import time by the integration
# tests and only this venv is guaranteed provisioned (requirements.txt).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="$REPO_ROOT/cryptobot/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "ERROR: $PY not found — create it (python -m venv) and install -r requirements.txt" >&2
  exit 1
fi
cd "$REPO_ROOT"
exec "$PY" -m pytest cryptobot/tests options/tests -q "$@"
