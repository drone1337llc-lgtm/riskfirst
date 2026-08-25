# cryptobot — LLM-gated RL crypto paper-trader

Local Ollama (Windows, 7900 XTX) classifies the macro regime and sets an
allocation cap. A PPO policy trained in a TensorTrade env picks a target
exposure each 15-min bar. Execution rebalances an Alpaca **paper** account,
hard-capped by the LLM's `max_allocation`. Paper-only is enforced in
`config.py` and `bot/execute.py`.

## Layout
- `config.py` — symbols, risk params, intervals, env vars
- `bot/data.py` — Alpaca crypto bars + features (shared by training and live)
- `bot/macro.py` — Ollama regime JSON (schema-constrained), safe fallback
- `bot/env.py` — TensorTrade env: TargetAllocation actions, drawdown-penalized reward
- `bot/train.py` — PPO training (local CPU or RunPod GPU)
- `bot/execute.py` — Alpaca paper rebalancing + guardrail (min(agent, LLM cap))
- `bot/run.py` — 24/7 loop with backoff-retry; writes `state/status.json`
- `runpod/` — pod training + checkpoint sync scripts

## Setup
1. `cp .env.example .env` and add Alpaca **paper** keys (app.alpaca.markets → Paper).
2. Ollama on Windows must be reachable (auto-resolved via WSL gateway).
   Model: `ollama pull qwen2.5:14b`.
3. Smoke test: `.venv/bin/python smoke_test.py`

## Train
- Quick local (CPU): `.venv/bin/python -m bot.train --timesteps 30000 --device cpu`
- Real run (RunPod GPU pod):
  1. From WSL: `scp -P <port> -r ~/projects/cryptobot root@<pod-ip>:/workspace/`
  2. On pod: `bash /workspace/cryptobot/runpod/train_runpod.sh 2000000`
  3. Local: `bash runpod/sync_checkpoint.sh <port> <pod-ip>` then restart the bot.

## Run 24/7 (WSL systemd)
```bash
sudo cp cryptobot.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now cryptobot
journalctl -u cryptobot -f          # logs
cat state/status.json               # latest decision
```
Ensure WSL stays alive: on Windows, `wsl --manage Ubuntu --set-default` and keep a
terminal open, or set `[boot] systemd=true` in /etc/wsl.conf (already required) and
use Task Scheduler to run `wsl.exe -d Ubuntu true` at logon.

## Safety
- Paper-only asserted at import; live endpoints unreachable.
- Order size = min(agent request, cash × LLM max_allocation).
- LLM unreachable → conservative default (volatile, cap 0.25).
- Crash/network loss → exponential backoff, systemd auto-restart.
