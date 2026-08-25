#!/usr/bin/env bash
# Poll GPU-box training; when ALL symbols are done, pull checkpoints and restart bots.
# Usage: bash gpubox/check_train.sh [symbols...]
set -euo pipefail
if [ $# -eq 0 ]; then SYMBOLS=(ETH-USD SOL-USD); else SYMBOLS=("$@"); fi
HOST="surge@192.168.68.36"
SSHOPTS="-o BatchMode=yes -o ConnectTimeout=10"

ALL_DONE=1
for SYM in "${SYMBOLS[@]}"; do
  if ssh $SSHOPTS "$HOST" "grep -q 'saved checkpoint' ~/cryptobot-train/train_${SYM}.log 2>/dev/null"; then
    echo "$SYM: done"
  else
    echo "$SYM: training --- $(ssh $SSHOPTS "$HOST" "tail -c 200 ~/cryptobot-train/train_${SYM}.log 2>/dev/null | tr '\n' ' ' | tail -c 120" || echo no-log)"
    ALL_DONE=0
  fi
done

if [ "$ALL_DONE" = "1" ]; then
  for SYM in "${SYMBOLS[@]}"; do
    F="ppo_${SYM//-/}.zip"
    scp $SSHOPTS "$HOST:~/cryptobot-train/cryptobot/checkpoints/$F" \
        ~/projects/cryptobot/checkpoints/"$F"
    echo "synced $F"
  done
  sudo -n systemctl restart cryptobot 2>/dev/null && echo "cryptobot (ETH) restarted" || \
    echo "RUN MANUALLY: sudo systemctl restart cryptobot"
  for SYM in "${SYMBOLS[@]}"; do
    [ "$SYM" = "ETH-USD" ] && continue
    sudo -n systemctl restart "cryptobot@${SYM}" 2>/dev/null && echo "cryptobot@${SYM} restarted" || \
      echo "NOT RUNNING YET: cryptobot@${SYM} (install template unit first)"
  done
  echo SYNCED
else
  echo STILL_TRAINING
fi
