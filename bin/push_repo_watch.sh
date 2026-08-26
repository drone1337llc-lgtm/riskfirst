#!/bin/bash
# Auto-publish: fires once the public repo can actually be pushed.
# Two unblock paths:
#   1. Surge drops a PAT at /home/surge/.gh-token OR runs `gh auth login`
#      -> token path: gh repo create (if needed) + push
#   2. Surge creates drone1337llc-lgtm/riskfirst on the web (SSH auth already works)
#      -> SSH path: attach origin + push, no token needed
# Mirrors alpaca_key_watch.sh: one-shot flag, everything logged.
# FIX 2026-08-26: flag now set ONLY on verified push success (was: touched
# before push -> transient 401/create-race left a spuriously-set flag and the
# watcher went permanently silent; repo never shipped).
FLAG=/home/surge/cryptobot-train/.repo_pushed_fired
LOG=/home/surge/cryptobot-train/repo_push.log
REPO=drone1337llc-lgtm/riskfirst
SSH_URL=git@github.com:drone1337llc-lgtm/riskfirst.git
NOW=$(date '+%Y-%m-%dT%H:%M:%S%z')

[ -f "$FLAG" ] && exit 0

# 1) feed a dropped token to gh (idempotent, silent)
if [ -f /home/surge/.gh-token ]; then
  gh auth login --hostname github.com --with-token < /home/surge/.gh-token 2>/dev/null || true
fi
# REAL gate: gh api user does a live authenticated call.
# `gh auth status` is NOT a valid gate (exit 0 even on 401 with a broken token).
TOKEN_OK=0
if gh api user >/dev/null 2>&1; then TOKEN_OK=1; fi

# 2) repo already exists on GitHub (creation done via web or earlier token run)?
REPO_EXISTS=0
if git ls-remote "$SSH_URL" >/dev/null 2>&1; then REPO_EXISTS=1; fi

# neither a valid token nor an existing repo -> nothing to do, stay silent
if [ "$TOKEN_OK" -eq 0 ] && [ "$REPO_EXISTS" -eq 0 ]; then
  exit 0
fi

PUSH_OK=0
{
  echo "=== REPO PUSH $NOW (token_ok=$TOKEN_OK repo_exists=$REPO_EXISTS) ==="
  cd /home/surge/cryptobot-train || exit 1
  if [ "$REPO_EXISTS" -eq 0 ]; then
    gh repo create "$REPO" --public --source=. --remote origin --push --description "RiskFirst: An Options and Equities Agent on Alpaca MCP with a Walk-Forward OOS Gate" && PUSH_OK=1 || echo "CREATE_FAILED (will retry)"
  else
    git remote add origin "$SSH_URL" 2>/dev/null || git remote set-url origin "$SSH_URL"
    if git push -u origin HEAD; then PUSH_OK=1; else echo "PUSH_FAILED (will retry)"; fi
  fi
  echo "--- remote ---"
  git remote -v
  echo "--- public ---"
  if [ "$TOKEN_OK" -eq 1 ]; then
    gh repo view "$REPO" --json visibility,url 2>&1
  else
    echo "no token; repo exists via SSH (created on web)"
  fi
  if [ "$PUSH_OK" -eq 1 ]; then
    touch "$FLAG"
    echo "=== WATCH DONE (flag set) $NOW ==="
  else
    echo "=== WATCH RETRY PENDING (no flag) $NOW ==="
  fi
} >> "$LOG" 2>&1
