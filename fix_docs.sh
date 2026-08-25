#!/bin/bash
# Fix key-free doc gaps in the Alpaca hackathon submission kit (2026-08-25 05:0x MDT).
# 1. SUBMISSION.md: document the PRIMARY options lane key-free run path (was equity-only).
# 2. options/README.md: purge the local Windows machine path + stale 36-test count.
set -euo pipefail
cd /home/surge/cryptobot-train

# --- SUBMISSION.md: add options lane to "Run it yourself" ---
python3 - <<'PY'
from pathlib import Path
p = Path("SUBMISSION.md")
s = p.read_text()
old = """## Run it yourself (key-free demo)

```
python -m pip install -r requirements.txt
cd cryptobot && .venv/bin/python -m bot.equity_agent --demo --symbol SPY
```

No Alpaca keys needed: bars come from yfinance, the option chain is synthetic"""
new = """## Run it yourself (key-free demo)

```
python -m pip install -r requirements.txt
cd cryptobot && .venv/bin/python -m bot.equity_agent --demo --symbol SPY   # equities lane
cd ../options && ../cryptobot/.venv/bin/python -m options.cli               # options lane (primary)
```

No Alpaca keys needed: the equities lane pulls bars from yfinance with a
synthetic chain; the options lane runs its full decision cycle
(bull/bear/neutral agents -> risk arbiter -> LLM referee advisory review)
against a mock broker, and the SAME guardrails run as the paper path
(`_guard_legs`: 2-4 unique legs, $500/leg cap, $1 floor, intent whitelist)
with fills labeled SIMULATED. Swap in paper keys and the identical
order-builder hits the real Alpaca paper API via MCP."""
assert old in s, "SUBMISSION.md anchor not found"
p.write_text(s.replace(old, new, 1))
print("SUBMISSION.md patched")
PY

# --- options/README.md: purge Windows path + fix stale "36 passed" ---
python3 - <<'PY'
from pathlib import Path
p = Path("options/README.md")
s = p.read_text()
old = """```bash
cd C:\\Users\\Tench\\.openclaw\\workspace\\alpaca-hackathon\\options
python -m pytest -q                       # → 36 passed (offline)
python -c "import options.agent; print('import ok')"
```"""
new = """```bash
cd options
python -m pytest -q                       # → 50 passed (offline)
python -c "import options.agent; print('import ok')"
```"""
assert old in s, "options/README.md path anchor not found"
p.write_text(s.replace(old, new, 1))
print("options/README.md patched")
PY

git add -A && git commit -q -m "docs: submission + options README now show the key-free options lane entry point; purge machine path + stale test count" && git log --oneline -1
