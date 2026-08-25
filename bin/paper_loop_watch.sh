#!/bin/bash
# paper_loop_watch.sh — keeps the paper-lane runner alive for the judging
# window (Aug 28 - Sep 4). Fully INERT until Alpaca paper keys land (the
# .keys_landed_fired flag is set by alpaca_key_watch.sh); afterwards:
#   - runner dead (stale pid)            -> restart via start_paper_loop.sh
#   - runner wedged (pid alive but no status.json write for 15 min during
#     NY RTH 09:30-16:00)                -> SIGTERM, wait, restart
# Idempotent; safe to run every minute from cron (flock-serialized).
set -uo pipefail

REPO=/home/surge/cryptobot-train
ENV_FILE=$REPO/.env
FLAG=$REPO/.keys_landed_fired
LOG=$REPO/state/paper/paper_loop_watch.log
PIDFILE=$REPO/state/paper/paper_loop.pid
STATUS=$REPO/state/paper/status.json

mkdir -p "$REPO/state/paper"

# Pre-keys era: nothing to supervise.
[ -f "$FLAG" ] || exit 0
[ -f "$ENV_FILE" ] || exit 0

# Serialize cron invocations (no double-restart).
exec 9>>"$LOG"
flock -n 9 2>/dev/null || exit 0

NOW=$(date '+%Y-%m-%dT%H:%M:%S%z')

# --- is the runner alive? ---
ALIVE=0
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  ALIVE=1
fi

# --- is it wedged? (no status write for 15 min during NY RTH) ---
WEDGED=0
AGE=0
DOW=$(TZ=America/New_York date +%u)        # 1=Mon .. 7=Sun
HM=$(TZ=America/New_York date +%H%M)
if [ "$DOW" -le 5 ] && [ "$HM" -ge 0930 ] && [ "$HM" -le 1600 ]; then
  if [ -f "$STATUS" ]; then
    AGE=$(( $(date +%s) - $(stat -c %Y "$STATUS") ))
    [ "$AGE" -gt 900 ] && WEDGED=1
  fi
fi

if [ "$ALIVE" -eq 1 ] && [ "$WEDGED" -eq 0 ]; then
  exit 0
fi

if [ "$ALIVE" -eq 1 ] && [ "$WEDGED" -eq 1 ]; then
  echo "$NOW paper loop WEDGED (status.json ${AGE}s stale) — SIGTERM" >> "$LOG"
  kill -TERM "$(cat "$PIDFILE")" 2>/dev/null
  sleep 3
fi

echo "$NOW paper loop dead/wedged — restarting" >> "$LOG"
bash "$REPO/bin/start_paper_loop.sh" >> "$LOG" 2>&1
