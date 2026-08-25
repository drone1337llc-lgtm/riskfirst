# ALPACA HACKATHON — PROJECT TITLE & DESCRIPTION

## Title
**VOLTAIR — The Autonomous Options Agent**

*An LLM-orchestrated, multi-agent paper-options trader that turns IV rank and volatility risk premium into defined-risk income — and refuses to trade when the math doesn't pay.*

---

## Hook (1–2 sentences)

VOLTAIR is an **autonomous AI agent** — not a script — that runs a bull / bear / neutral debate through an LLM risk arbiter, reads live Alpaca option chains via MCP, picks a Level-3-legal options structure by **IV rank**, and sizes every idea at **≤2% equity** behind a hard suite of risk gates. It harvests theta when implied volatility is rich and buys cheap protection when it's low — capturing the volatility risk premium that flat long-only returns can't.

---

## Detailed Description (what the judges read)

### The problem
Most "AI trading bots" are single-signal scripts that go long, bleed in choppy tape, and have **no definition of risk**. Worse, most Alpaca submissions never use options — which is the entire point of an *options* hackathon. And of the ones that do, almost none behave like an agent: they execute a fixed rule with no reasoning, no market-regime judgment, and no guardrail against a −8% drawdown.

VOLTAIR was built to be the opposite: a system that **debates**, **decides**, **sizes**, and **protects** — with every decision auditable to SQLite and every trade behind a non-negotiable risk arbiter.

### Why it's an autonomous AI agent (not a script)
VOLTAIR is a **multi-agent system with an LLM at the decision center**:

- **Bull sub-agent** proposes **covered calls** — sell an OTM call (~Δ0.25, ~21 DTE) against shares it already holds, harvesting theta + volatility premium when implied vol is rich.
- **Bear sub-agent** proposes a **protective put / credit collar** — buy an OTM put on SPY to cap drawdown on the long book, funded by selling an OTM call → a near-zero-cost hedge when implied vol is cheap.
- **Neutral/Income sub-agent** proposes a **cash-secured put** — sell an OTM put, fully cash-collateralized, to buy dips at a discount while collecting premium.
- **IV-Rank Scorer** — computes each underlying's implied-vol percentile from chain history and routes the debate: **high IVR → sell premium (bull/neutral); low IVR → buy cheap protection (bear).** This is the agent's market-condition judgment.
- **Risk Arbiter** — the referee. **Every** proposal must clear it before any order is placed. It enforces the risk framework below and records rejections as loudly as fills.
- **LLM Referee** — the LLM at the decision center. Every proposal the arbiter accepts is then reviewed by a local LLM (Ollama, `qwen2.5:1.5b` — small enough to run alongside the stack) whose verdict and reasoning land in the same SQLite audit log. Advisory by default: the hard gates in code do the enforcing, so the LLM can never silently approve or block a trade; it is the qualitative second set of eyes that makes the decision log an honest narrative.

The agent **reasons about market conditions** — not hardcoded entry rules — because the structure *selection* is driven by IV rank, and the *sizing* is driven by a live portfolio risk model.

### Why it's an *options* agent
Options express conviction with **defined risk** and monetize **time decay**. VOLTAIR's core thesis: *equities drift, but options harvest the volatility-risk premium.* P&L is a first-class judging criterion, so every trade carries an explicit, capped risk-reward — never a naked bet. All structures are strictly **Alpaca Level-3-paper-legal** (covered calls, cash-secured puts, long puts/calls, debit spreads) — **no naked shorts**, ever.

### How it uses Alpaca (MCP / CLI)
VOLTAIR trades through the **Alpaca MCP server** (Dockerized `ghcr.io/alpacahq/alpaca-mcp`) via a typed wrapper (`client.py`), reading `/v2/options/contracts` chains and submitting orders to a **fresh paper account** — the one required by the rules. It is fully **offline-testable** against a deterministic `MockClient` so risk logic and Greeks are verified with zero keys and zero network before a single paper dollar is at risk.

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
The crypto-momentum core (**Cryptonaut**) was diagnosed to three real loss drivers and gated behind a **walk-forward out-of-sample evaluator** that showed **positive OOS Sharpe**. That same discipline — **never claim an edge you haven't validated OOS** — governs VOLTAIR: every structure and gate is unit-tested offline (**77 passing tests** covering Black-Scholes Greeks, put-call parity, IV recovery, 2% sizing, drawdown blocks, spread/OI screens, MCP contract parsing, and the LLM referee), so the live paper track record is *measured*, not manufactured.

**Built to the actual scoring criteria**: options-as-core (mandatory), MCP/CLI (mandatory), multi-agent LLM reasoning, risk gates, and an auditable SQLite decision log (`decisions.db`) that turns every trade and every rejection into a P&L narrative.

---

*VOLTAIR — debate the market, define the risk, harvest the premium, and never over-trade into a drawdown.*
