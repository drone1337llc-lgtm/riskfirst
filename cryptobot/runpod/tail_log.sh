#!/usr/bin/env bash
set -euo pipefail
KEY=~/.runpod/ssh/runpodctl-ssh-key
SSHOPTS="-i $KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 -o LogLevel=ERROR"
read -r IP PORT < ~/projects/cryptobot/state/pod_addr
ssh $SSHOPTS -p "$PORT" "root@$IP" \
  "tail -n ${1:-8} /workspace/train.log 2>/dev/null || echo NO_LOG_YET; pgrep -f bot.train >/dev/null && echo TRAIN_RUNNING || echo TRAIN_NOT_RUNNING"
