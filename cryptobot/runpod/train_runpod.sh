#!/usr/bin/env bash
# Run ON the RunPod pod (NVIDIA GPU image, e.g. runpod/pytorch:2.*-cuda12*).
# Usage: bash train_runpod.sh [timesteps]
set -euo pipefail
TIMESTEPS="${1:-1000000}"

cd /workspace
if [ ! -d cryptobot ]; then
  echo "Copy the project first: runpodctl send / scp -P <port> -r cryptobot root@<pod-ip>:/workspace/"
  exit 1
fi
cd cryptobot

pip install -q 'numpy<2' 'pandas<2.1' tensortrade 'gym==0.25.2' \
  stable-baselines3 shimmy alpaca-py requests python-dotenv
# tensorflow (tensortrade agents dep) clashes with torch -> segfault; we use SB3
pip uninstall -qy tensorflow || true
python - <<'EOF'
import pathlib
from importlib.util import find_spec
p = pathlib.Path(find_spec("tensortrade").origin)
s = p.read_text()
if "except ModuleNotFoundError" not in s:
    s = s.replace("from . import agents",
                  "try:\n    from . import agents\nexcept ModuleNotFoundError:\n    agents = None")
    p.write_text(s)
EOF

python -m bot.train --timesteps "$TIMESTEPS" --device cuda --out checkpoints/ppo_policy.zip
echo "Done. Pull the checkpoint back with runpod/sync_checkpoint.sh"
