#!/usr/bin/env bash
# Run LOCALLY (WSL). Pulls the trained checkpoint down from the pod over SSH.
# Usage: bash runpod/sync_checkpoint.sh <pod-ssh-port> <pod-ip>
set -euo pipefail
PORT="${1:?ssh port}" ; IP="${2:?pod ip}"
scp -P "$PORT" "root@${IP}:/workspace/cryptobot/checkpoints/ppo_policy.zip" \
  "$(dirname "$0")/../checkpoints/ppo_policy.zip"
echo "checkpoint synced -> checkpoints/ppo_policy.zip (restart the bot to load it)"
