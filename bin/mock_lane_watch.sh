#!/bin/bash
# mock_lane_watch.sh — keeps the KEY-FREE mock demo lane producing fresh
# evidence during NY RTH (09:30-16:00 Mon-Fri). Runs one dry-run cycle per
# ~30 min via the runner's --mock --once path.
#
# Why: the submission needs to show a live agent at work even BEFORE Alpaca
# keys land. The mock lane is the judge-facing demo of the exact options
# agent that the paper lane runs (same strategies, same risk arbiter, same
# audit schema) — but it writes ONLY to state/mock/, NEVER to the live
# state/paper/ audit trail that becomes the real paper P&L once keys land.
#
# Idempotent; safe to run every minute from cron (flock-serialized).
set -uo pipefail

REPO=/home/surge/cryptobot-train
PY=$REPO/cryptobot/.venv/bin/python
LOG=$REPO/state/mock/paper_loop_watch.log
STATUS=$REPO/state/mock/status.json
STALE_AFTER=300   # seconds; re-run a cycle if the last one is older

mkdir -p "$REPO/state/mock"

# Serialize cron invocations (no double-run).
exec 9>>"$LOG"
flock -n 9 2>/dev/null || exit 0

NOW=$(date '+%Y-%m-%dT%H:%M:%S%z')

# RTH gate (same clock as the real lane).
DOW=$(TZ=America/New_York date +%u)        # 1=Mon .. 7=Sun
HM=$(TZ=America/New_York date +%H%M)
if [ "$DOW" -gt 5 ] || [ "$HM" -lt 0930 ] || [ "$HM" -gt 1600 ]; then
  exit 0
fi

# Staleness gate: skip if a fresh cycle already ran.
if [ -f "$STATUS" ]; then
  AGE=$(( $(date +%s) - $(stat -c %Y "$STATUS") ))
  [ "$AGE" -lt "$STALE_AFTER" ] && exit 0
fi

# NOTE: the runner package lives under options/options/runner.py — it must be
# invoked with CWD=options/ (mirrors start_paper_loop.sh). `-m options.runner`
# from the repo root fails with "No module named options.runner".
cd "$REPO/options"
if "$PY" -m options.runner --mock --once >> "$LOG" 2>&1; then
  echo "$NOW mock cycle OK" >> "$LOG"
else
  echo "$NOW mock cycle FAILED (rc=$?)" >> "$LOG"
fi
