#!/usr/bin/env bash
# Fully automated: wait for pod, push code, launch detached training.
# Usage: bash runpod/auto_train.sh <pod-id> [timesteps]
set -euo pipefail
POD="${1:?pod id}"; STEPS="${2:-2000000}"
RP=~/.local/bin/runpodctl
KEY=~/.runpod/ssh/runpodctl-ssh-key
SSHOPTS="-i $KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"

echo "waiting for pod $POD ..."
for i in $(seq 1 40); do
  INFO=$($RP get pod "$POD" -a 2>/dev/null || true)
  ADDR=$(echo "$INFO" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+->22' | head -1 || true)
  if [ -n "$ADDR" ] && echo "$INFO" | grep -q RUNNING; then break; fi
  sleep 15
done
[ -n "${ADDR:-}" ] || { echo "pod never became reachable"; exit 1; }
IP="${ADDR%%:*}"; PORT_MAP="${ADDR#*:}"; PORT="${PORT_MAP%%->*}"
echo "pod up at $IP:$PORT"

for i in $(seq 1 20); do
  ssh $SSHOPTS -p "$PORT" "root@$IP" true 2>/dev/null && break || sleep 10
done

cd ~/projects
tar --exclude=cryptobot/.venv --exclude=cryptobot/.env --exclude=cryptobot/state \
    --exclude=cryptobot/checkpoints --exclude=cryptobot/__pycache__ \
    --exclude=cryptobot/bot/__pycache__ \
    -czf /tmp/cryptobot.tar.gz cryptobot
echo "$IP $PORT" > ~/projects/cryptobot/state/pod_addr
scp $SSHOPTS -P "$PORT" /tmp/cryptobot.tar.gz "root@$IP:/workspace/"
ssh $SSHOPTS -p "$PORT" "root@$IP" \
  "cd /workspace && tar xzf cryptobot.tar.gz --no-same-owner && \
   nohup bash cryptobot/runpod/train_runpod.sh $STEPS > /workspace/train.log 2>&1 < /dev/null & \
   echo TRAINING_LAUNCHED"
echo DONE
