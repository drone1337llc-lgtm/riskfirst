#!/usr/bin/env bash
# Runs ON the GPU box (fed over ssh stdin). Args: STEPS SYMBOL [SYMBOL...]
set -euo pipefail
STEPS="$1"; shift; SYMBOLS=("$@")

mkdir -p ~/cryptobot-train && cd ~/cryptobot-train
rm -rf cryptobot
tar xzf /tmp/cryptobot.tar.gz --no-same-owner
cd cryptobot

command -v ~/.local/bin/uv >/dev/null 2>&1 || \
  curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
UV=~/.local/bin/uv
[ -d .venv ] || $UV venv --python 3.10 .venv >/dev/null
$UV pip install -q --python .venv/bin/python 'numpy<2' 'pandas<2.1' torch \
  tensortrade 'gym==0.25.2' stable-baselines3 shimmy alpaca-py requests python-dotenv

# tensorflow (tensortrade agents dep) clashes with torch -> segfault; we use SB3
$UV pip uninstall -q --python .venv/bin/python tensorflow 2>/dev/null || true
.venv/bin/python - <<'EOF'
import pathlib
from importlib.util import find_spec
p = pathlib.Path(find_spec("tensortrade").origin)
s = p.read_text()
if "except ModuleNotFoundError" not in s:
    s = s.replace("from . import agents",
                  "try:\n    from . import agents\nexcept ModuleNotFoundError:\n    agents = None")
    p.write_text(s)
EOF

mkdir -p checkpoints
i=0
for SYM in "${SYMBOLS[@]}"; do
  LOG=~/cryptobot-train/train_${SYM}.log
  CUDA_VISIBLE_DEVICES=$i CRYPTOBOT_SYMBOL=$SYM \
    nohup .venv/bin/python -m bot.train --timesteps "$STEPS" --device cuda \
    > "$LOG" 2>&1 < /dev/null &
  echo "launched $SYM on GPU $i (log: $LOG)"
  i=$(( (i + 1) % 2 ))
done
echo ALL_LAUNCHED
