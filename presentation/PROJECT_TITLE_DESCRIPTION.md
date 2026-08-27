# ALPACA HACKATHON — PROJECT TITLE & DESCRIPTION

## Title
**RiskFirst — An Options & Equities Agent on Alpaca MCP with a Walk-Forward OOS Gate**

*An LLM-orchestrated, multi-agent paper-options trader that turns IV rank and volatility risk premium into defined-risk income — and refuses to trade when the math doesn't pay.*

---

## Hook (1–2 sentences)

RiskFirst is an **autonomous AI agent** — not a script — that runs a bull / bear / neutral debate through an LLM risk arbiter, reads live Alpaca option chains via MCP, picks a Level-3-legal options structure by **IV rank**, and sizes every idea at **≤2% equity** behind a hard suite of risk gates. It harvests theta when implied volatility is rich and buys cheap protection when it's low — and a **walk-forward out-of-sample gate** decides what gets to trade at all.

---

## Detailed Description (what the judges read)

### The problem
Most "AI trading bots" are single-signal scripts that go long, bleed in choppy tape, and have **no definition of risk**. Worse, most Alpaca submissions never use options — which is the entire point of an *options* hackathon. And of the ones that do, almost none behave like an agent: they execute a fixed rule with no reasoning, no market-regime judgment, and no guardrail against a drawdown.

RiskFirst was built to be the opposite: a system that **debates**, **decides**, **sizes**, and **protects** — with every decision auditable to SQLite and every trade behind a non-negotiable risk arbiter.

### Why it's an autonomous AI agent (not a script)
RiskFirst is a **multi-agent system with an LLM at the decision center**:

- **Bull sub-agent** proposes **covered calls** — sell an OTM call (~Δ0.25, ~21 DTE) against shares it already holds, harvesting theta + volatility premium when implied vol is rich.
- **Bear sub-agent** proposes a **protective put / credit collar** — buy an OTM put on SPY to cap drawdown on the long book, funded by selling an OTM call → a near-zero-cost hedge when implied vol is cheap.
- **Neutral/Income sub-agent** proposes a **cash-secured put** — sell an OTM put, fully cash-collateralized, to buy dips at a discount while collecting premium.
- **IV-Rank Scorer** — computes each underlying's implied-vol percentile from chain history and routes the debate: **high IVR → sell premium (bull/neutral); low IVR → buy cheap protection (bear).** This is the agent's market-condition judgment.
- **Risk Arbiter** — the referee. **Every** proposal must clear it before any order is placed. It enforces the risk framework below and records rejections as loudly as fills.
- **LLM Referee** — the LLM at the decision center. Every proposal the arbiter accepts is then reviewed by a local LLM (Ollama, `qwen2.5:1.5b` — small enough to run alongside the stack on a 24 GB GPU) whose verdict and reasoning land in the same SQLite audit log. Advisory by default: the hard gates in code do the enforcing, so the LLM can never silently approve or block a trade; it is the qualitative second set of eyes that makes the decision log an honest narrative.

The agent **reasons about market conditions** — not hardcoded entry rules — because the structure *selection* is driven by IV rank, and the *sizing* is driven by a live portfolio risk model.

### Why it's an *options* agent
Options express conviction with **defined risk** and monetize **time decay**. RiskFirst's core thesis: *equities drift, but options harvest the volatility-risk premium.* P&L is a first-class judging criterion, so every trade carries an explicit, capped risk-reward — never a naked bet. All structures are strictly **Alpaca Level-3-paper-legal** (covered calls, cash-secured puts, long puts/calls, debit spreads) — **no naked shorts**, ever.

### How it uses Alpaca (MCP / CLI)
RiskFirst trades through the **Alpaca MCP server** (`uvx alpaca-mcp-server`, launcher `bin/run_mcp.sh` — stdio / streamable-http / SSE) via a typed wrapper (`options/client.py`), every call an MCP tool: account reads, option-chain reads, multi-leg order placement, and a `close_all_positions` circuit-breaker. **Paper is hard-forced inside the client's server env** (`ALPACA_PAPER=true`) — a live key cannot reach a real account even by misconfiguration. It is fully **offline-testable** against a deterministic `MockClient` so risk logic and Greeks are verified with zero keys and zero network before a single paper dollar is at risk.

### The risk framework (non-negotiable, arbiter-enforced)

| Gate | Value |
|------|-------|
| Position size | **≤ 2%** equity per trade |
| Daily loss circuit | **−3%** intraday → flatten + halt |
| Drawdown pause | **−8%** from equity high → stop trading |
| Min open interest | **≥ 100** contracts |
| Max bid/ask spread | **≤ $0.15** |
| Net delta cap | **±0.30** portfolio |
| Options weight | ≤ **30%** of equity |
| Cash reserve | **10%** buffer |

### P&L story (honest, defensible)
An adversarial design review on day 0 found our existing crypto-momentum core (**Cryptonaut**) had three real loss drivers — train↔live simulation mismatch (3% sim commission paper never pays), long-only with zero walk-forward validation, and a macro gate that added no edge. We fixed the process before adding features: commission→0, drawdown lambda 3.0→0.4, 5-min live cadence — and built a **walk-forward out-of-sample evaluator** (`eval_oos.py`, 75/25 windows, 4 folds, ~300k timesteps) as the hard gate: **the crypto lane stays only if OOS Sharpe is positive net.** Spec run: mean annualized Sharpe **2.35** (seed-42 deterministic), folds **[-2.43, 14.57, -2.86, 0.13]** — 2/4 negative, PASS (kept as the honestly-framed secondary lane; noisy folds are exactly why it is not the primary). That same discipline — **never claim an edge you haven't validated OOS** — governs RiskFirst: **133 offline tests pass** (60 cryptobot + 73 options covering MCP contract, LLM referee, and the paper-loop runner), so the live paper track record is *measured*, not manufactured.

**Built to the actual scoring criteria**: options-as-core (mandatory), MCP/CLI (mandatory), multi-agent LLM reasoning, quantified risk rails, and an auditable SQLite decision log (`decisions.db`) that turns every trade and every rejection into a P&L narrative.

---

*RiskFirst — the gate decides what trades, the arbiter decides what ships, the log proves both.*
