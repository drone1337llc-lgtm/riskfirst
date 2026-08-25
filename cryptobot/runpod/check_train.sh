#!/usr/bin/env bash
# Poll training; when checkpoint exists, pull it, terminate pod, restart bot.
# Usage: bash runpod/check_train.sh <pod-id>
set -euo pipefail
POD="${1:?pod id}"
RP=~/.local/bin/runpodctl
KEY=~/.runpod/ssh/runpodctl-ssh-key
SSHOPTS="-i $KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"
read -r IP PORT < ~/projects/cryptobot/state/pod_addr

if ssh $SSHOPTS -p "$PORT" "root@$IP" grep -q 'saved checkpoint' /workspace/train.log 2>/dev/null; then
  echo "checkpoint ready — syncing"
  scp $SSHOPTS -P "$PORT" "root@$IP:/workspace/cryptobot/checkpoints/ppo_policy.zip" \
      ~/projects/cryptobot/checkpoints/ppo_policy.zip
  echo "terminating pod $POD"
  $RP remove pod "$POD"
  sudo -n systemctl restart cryptobot 2>/dev/null && echo "bot restarted" || \
    echo "RUN MANUALLY: sudo systemctl restart cryptobot"
  echo SYNCED
else
  echo "--- last log lines ---"
  ssh $SSHOPTS -p "$PORT" "root@$IP" tail -5 /workspace/train.log || true
  echo STILL_TRAINING
fi
