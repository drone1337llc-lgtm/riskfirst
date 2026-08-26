#!/bin/bash
# dr_backup.sh - refresh off-box disaster-recovery artifacts for the RiskFirst Alpaca kit.
# Creates a git bundle (full history) + runtime tarball (decisions.db, paper state, logs,
# fresh P&L export) under ~/cryptobot-backups/. Pull to teamamd with:
#   scp surge@192.168.68.67:~/cryptobot-backups/*.<ext> "C:\Users\Tench\.openclaw\workspace\backups\alpaca-kit\"
set -e
cd /home/surge/cryptobot-train
STAMP=$(date -u +%Y%m%d-%H%M%S)
OUTDIR=/home/surge/cryptobot-backups
mkdir -p "$OUTDIR"
KIT="$OUTDIR/cryptobot-kit-${STAMP}.bundle"
RUNTIME="$OUTDIR/cryptobot-runtime-${STAMP}.tgz"

# 0) regenerate the P&L export so the backup always carries a current report
#    (live audit trail is state/paper/decisions.db — the runner's STATE_DIR)
cryptobot/.venv/bin/python bin/export_pnl.py --mode PAPER >/dev/null 2>&1 || true

# 1) full git history bundle
git bundle create "$KIT" --all
git bundle verify "$KIT" >/dev/null

# 2) runtime state: LIVE decisions.db (P&L track record) + status.json + loop logs
#    NOTE: options/decisions.db is a STALE pre-state leftover — never ship it.
tar -czf "$RUNTIME" \
  state/paper/decisions.db \
  state/paper/status.json \
  state/paper/pnl_report.md \
  state/paper/pnl_stats.json \
  state/paper/paper_loop.log \
  state/paper/paper_loop_watch.log \
  state/mock/decisions.db \
  state/mock/status.json \
  state/mock/pnl_report.md \
  state/mock/pnl_stats.json \
  state/mock/paper_loop.log \
  state/mock/paper_loop_watch.log \
  keys_landed.log \
  2>/dev/null || true
tar -tzf "$RUNTIME" >/dev/null

echo "DR_ARTIFACTS_READY:"
echo "  $KIT"
echo "  $RUNTIME"
