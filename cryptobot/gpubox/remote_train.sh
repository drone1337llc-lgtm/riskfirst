#!/usr/bin/env bash
# Push code to the GPU box and train one policy per symbol, one per GPU.
# Usage: bash gpubox/remote_train.sh [timesteps] [symbols...]
set -euo pipefail
STEPS="${1:-2000000}"; shift || true
if [ $# -eq 0 ]; then SYMBOLS=(ETH-USD SOL-USD); else SYMBOLS=("$@"); fi
HOST="surge@192.168.68.36"
SSHOPTS="-o BatchMode=yes -o ConnectTimeout=10"

cd ~/projects
tar --exclude=cryptobot/.venv --exclude=cryptobot/.env --exclude=cryptobot/state \
    --exclude=cryptobot/checkpoints --exclude=cryptobot/__pycache__ \
    --exclude=cryptobot/bot/__pycache__ -czf /tmp/cryptobot.tar.gz cryptobot
scp $SSHOPTS /tmp/cryptobot.tar.gz "$HOST:/tmp/"
ssh $SSHOPTS "$HOST" bash -s -- "$STEPS" "${SYMBOLS[@]}" \
    < ~/projects/cryptobot/gpubox/remote_setup.sh
echo LAUNCHED
