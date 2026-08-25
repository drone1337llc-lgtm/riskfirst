# Alpaca AI Trading Agents — Submission Kit

**Deadline:** Sep 4, 2026 15:00 UTC · **Track:** Options + Equities (MCP/CLI)
**Repo:** (public push pending Surge go — see README)

---

## Title (short)

> **RiskFirst: An Options & Equities Agent on Alpaca MCP with a Walk-Forward OOS Gate**

Alt (shorter):
> **RiskFirst — Options/Equities Trading Agent with a Walk-Forward OOS Gate**

## One-line description

> A risk-first paper-trading agent for options + equities built on the Alpaca MCP server — momentum/mean-reversion equity signals with vol-targeted sizing, a defensive options wheel overlay, a -10% circuit-breaker, and a walk-forward out-of-sample gate that decides what gets to trade at all.

## Long description (judge-facing)

**What it is.** A modular, risk-first agent stack that trades Alpaca **paper** accounts. The primary lane is an **equities + options agent** (`bot/equity_agent.py`) that:

- Scores a liquid equity universe (SPY, QQQ, AAPL, MSFT, NVDA) with momentum/mean-reversion signals and sizes positions **vol-targeted** (risk per position scaled by realized vol, not fixed notional).
- Runs a defensive **options wheel overlay** — cash-secured puts + covered calls — on the same liquid underlyings, so the agent has both a long-beta engine and a defined-risk income/hedge layer.
- Enforces hard guardrails **before** any order reaches the broker: max 4 unique legs per multi-leg order, only valid intents (BTO/BTC/STO/STC), $500 notional cap per leg, $1 minimum, and a **-10% trailing drawdown circuit-breaker** that forces the book flat until regime confirmation.
- Connects through the **Alpaca MCP server** (`uvx alpaca-mcp-server`, launcher in `bin/run_mcp.sh` — stdio / streamable-http / SSE) so the agent's market reads and order decisions are tool-visible and auditable, not a black box.

**How it was built (the honest part).** An adversarial design review on day 0 found the original crypto-only PPO bot was (a) a requirements mismatch for an options/equities/MCP hackathon and (b) trading with **zero out-of-sample validation**. We fixed the process before adding features:

1. **Killed the train↔live mismatch** — the training env charged 3% commission paper never pays (policy learned to hug cash); `COMMISSION=0`, `DRAWDOWN_LAMBDA=3.0→0.4`, `DECISION_INTERVAL_S=300` (act every 5 min live, still train on 1-min bars).
2. **Built a walk-forward OOS gate** (`eval_oos.py`, 75/25 train/eval windows, 4 folds, ~300k timesteps) — the crypto lane stays only if out-of-sample Sharpe is positive **net**. Spec-compliant full 300k run: mean annualized Sharpe **5.88**, folds **[0.41, −9.43, 5.58, 26.95]** — **1/4 negative**, PASS (the crypto lane stays as the honestly-framed secondary lane; the noisy folds are exactly why it is not the primary).
3. **Re-centered the submission** on the options + equities agent with an MCP tool surface — the crypto PPO is honestly framed as a *secondary* lane, kept only because it passed the gate.

**Why it's different.** Most entries demo a single strategy. This one is a **portfolio-operations stack**: a champion/challenger walk-forward promote loop (promote on OOS, not train loss), a hard OOS gate that vetoes strategy changes, an options overlay that can actually hedge, and a circuit-breaker that stops the bleeding. The story is *process + risk rails + honest validation*, not a hype backtest.

## Demo script (video, ~90s)

1. Start the MCP server (`bin/run_mcp.sh`), show the tool list via `uvx alpaca-mcp-server`.
2. Run the equities lane in paper: show the vol-targeted sizing decision for one symbol, one wheel option placement (e.g. a CSP on SPY) with leg caps enforced.
3. Show the guardrails firing: an over-leveraged order (5 legs / bad intent) rejected **before** the broker.
4. Show the OOS gate output: 4-fold walk-forward Sharpe table for the crypto lane — honest positive-but-noisy framing.
5. Close with the circuit-breaker: force a >-10% drawdown scenario, watch the agent go flat.

## Key numbers (honest, current)

- OOS walk-forward gate (75/25 window, 4 folds, 300k timesteps): mean ann. Sharpe **5.88**, folds **[0.41, −9.43, 5.58, 26.95]** (1/4 negative — high variance, hence secondary lane only).
- Risk rails: $500/leg notional cap, ≤4 legs/order, -10% DD circuit-breaker, $1 min.
- Foundation: 3%→0% commission train/live match, drawdown lambda 0.4, 5-min decision cadence.

## Repository layout

```
cryptobot/
  config.py              risk params, symbols, intervals (paper-only asserted)
  eval_oos.py            walk-forward OOS gate — the hard gate
  bot/
    data.py              Alpaca bars + features (shared train/live)
    equity_agent.py      options + equities paper lane (MCP/CLI-ready)
    env.py               TensorTrade env (TargetAllocation, drawdown-penalized)
    macro.py             Ollama regime classifier (schema-constrained JSON)
    train.py             PPO training
    execute.py           Alpaca paper execution + guardrails
    run.py               24/7 loop with backoff + circuit-breaker
bin/run_mcp.sh           Alpaca MCP server launcher (stdio/http/sse)
```

## Run it yourself (key-free demo)

```
python -m pip install -r requirements.txt
cd cryptobot && .venv/bin/python -m bot.equity_agent --demo --symbol SPY   # equities lane
cd ../options && ../cryptobot/.venv/bin/python -m options.cli               # options lane (primary)
```

No Alpaca keys needed: the equities lane pulls bars from yfinance with a
synthetic chain; the options lane runs its full decision cycle
(bull/bear/neutral agents -> risk arbiter -> LLM referee advisory review)
against a mock broker, and the SAME guardrails run as the paper path
(`_guard_legs`: 2-4 unique legs, $500/leg cap, $1 floor, intent whitelist)
with fills labeled SIMULATED. Swap in paper keys and the identical
order-builder hits the real Alpaca paper API via MCP.
(clearly labeled), the SAME guardrails run as the paper path (`_guard_legs`:
2-4 unique legs, $500/leg cap, $1 floor, intent whitelist), and the fill is
SIMULATED. Swap in paper keys and the identical order-builder hits the real
Alpaca paper API. Full guardrail suite: `python -m pytest` (77 tests: 27 cryptobot + 50 options — incl. Greeks, risk arbiter, MCP contract, and the LLM referee).

## Build-in-public (posts scheduled Aug 27 → Sep 3)

1. **Announce:** "I adversarial-reviewed my own bot and found it was built on a wrong assumption. Here's what a real options/equities entry for the Alpaca hackathon looks like." + the 3 foundation fixes.
2. **The gate:** "Your backtest means nothing without an out-of-sample gate. Here's our 4-fold walk-forward harness — and why the crypto lane got demoted."
3. **The MCP lane:** "Agent meets Alpaca MCP: our options/equities lane lives in tool space — leg caps, intent validation, $500/leg. Guardrails demo."
4. **The circuit-breaker:** "When the -10% trip fires, the book goes flat. Demo + why 'memory' is a process, not a vibe."
5. **Submission:** "Repo + video + paper account ID — here's what we shipped, and where it's honestly weak."

## Paper account ID

PENDING — blocked on Surge's Alpaca paper `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` (escalated, Telegram msg 353). The moment keys land: verify live data + a real paper option order, then insert ID here.
