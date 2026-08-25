# Alpaca AI Trading Agents — Options & Equities Agent (paper)

**Hackathon submission (Alpaca AI Trading Agents, Aug 28 – Sep 4, 2026).**

A modular, risk-first trading agent stack for **Alpaca paper trading** with two lanes:

1. **PRIMARY — Options + Equities agent** (`cryptobot/bot/equity_agent.py`)
   — momentum/mean-reversion equity signals with vol-targeted sizing, plus a
   defensive options overlay (cash-secured put / covered-call wheel) on liquid
   underlyings. Runs through the **Alpaca MCP server** (`bin/run_mcp.sh`).
2. **SECONDARY — LLM-gated crypto PPO lane** (`cryptobot/bot/`)
   TensorTrade PPO policy on 1-min bars, rebalancing every 5 min against an
   Alpaca paper account, hard-capped by an Ollama regime classifier.
   **Kept only because it passed a walk-forward out-of-sample gate.**

## Why two lanes

An adversarial design review (2026-08-24) found the original crypto-only bot was
a requirements mismatch for this hackathon (options + equities + MCP/CLI tracks)
and, worse, had **zero out-of-sample validation** — no way to know if any fix
worked. So:

- First we fixed the train↔live mismatch: the training env charged 3% commission
  that live paper never pays (making the policy hug cash), drawdown penalty was
  dominant, and the agent acted on 1-min noise. Config now matches paper reality:
  `COMMISSION=0`, `DRAWDOWN_LAMBDA=0.4`, `DECISION_INTERVAL_S=300` while still
  training on 1-min bars.
- Then we built `cryptobot/oos_eval.py`, a walk-forward, 4-fold out-of-sample
  evaluator, and made it a **hard gate**: crypto lane stays only if OOS Sharpe is
  positive net.
- Result: OOS mean annualized Sharpe **4.28** — but noisy across folds
  `[4.07, 20.21, -3.68, -3.46]`, 2/4 folds negative. **Verdict: viable but
  high-variance → crypto stays a secondary lane, the options/equities agent is
  the primary submission.**

## Layout

```
cryptobot/
  config.py              risk params, symbols, intervals (paper-only asserted)
  oos_eval.py            walk-forward OOS gate (the hard gate)
  bot/
    data.py              Alpaca bars + features (shared train/live)
    equity_agent.py      options + equities paper lane (MCP/CLI-ready)
    env.py               TensorTrade env (TargetAllocation, drawdown-penalized)
    macro.py             Ollama regime classifier (schema-constrained JSON)
    train.py             PPO training
    execute.py           Alpaca paper execution + guardrails
    run.py               24/7 loop with backoff + circuit-breaker
  state/                 live status + OOS eval results
bin/
  run_mcp.sh             uvx alpaca-mcp-server launcher (stdio/http/sse, --env-file)
```

## Setup

```bash
cp .env.example .env     # add Alpaca PAPER ALPACA_API_KEY / ALPACA_SECRET_KEY
pip install -r requirements.txt
python cryptobot/oos_eval.py        # walk-forward OOS gate
python -m cryptobot.bot.train --timesteps 300000 --device cpu
python -m cryptobot.bot.run         # 24/7 paper loop
```

## Risk rails (both lanes)

- **Paper-only enforced at import** — live endpoints unreachable.
- Notional caps ($500/leg options, aggregate delta ≤ 0.15) + min order floors.
- **Circuit breaker:** realized drawdown ≤ −10% → flat until regime confirmation.
- LLM unreachable → conservative fallback (max allocation 0.25).
- Champion/challenger walk-forward promote: a challenger only replaces the live
  lane on an OOS win, never on training loss.

## Honest status

- OOS gate: **PASS** (mean ann. Sharpe 4.28) with high variance — crypto lane
  kept as secondary.
- Options + equities lane: scaffolded and API-verified against alpaca-py 0.43.5
  (multi-leg `mleg` orders, `PositionIntent` BTO/BTC/STO/STC, ≤ 4 legs, option
  chains via `OptionHistoricalDataClient`).
- Live paper data/orders require Alpaca paper keys in `.env`.
