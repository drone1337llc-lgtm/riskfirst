# Alpaca Options Agent

**Autonomous paper options-trading agent** built for the *Alpaca AI Trading
Agents Hackathon* (lablab.ai). It scans US equity/ETF option chains (SPY/QQQ),
picks a paper-legal structure by **IV rank**, sizes at **≤2% equity**, gates
every idea behind a **risk arbiter**, and sends every accepted proposal to an
**LLM referee** (local Ollama) whose verdict is written to the SQLite audit
log — all decisions logged for an auditable P&L.

> **Paper only.** The real Alpaca MCP integration is wired but gated behind a
> `LIVE` flag. This scaffold builds and tests fully **offline** with no keys.

---

## Why options (the thesis)

Equities drift; **options express conviction with defined risk and time
decay.** A pure long-equity agent earns only when prices rise and bleeds in
choppy tape. An options overlay harvests premium when implied vol is rich
(IV rank high) and buys cheap protection when IV is low — capturing the
volatility-risk-premium that flat spot returns can't. P&L is a first-class
judging criterion, so every decision carries an explicit risk-reward trade.

Alpaca paper accounts support **Level 3** options: covered calls,
cash-secured puts, long calls/puts, and debit spreads — **no naked shorts**.
We stay strictly inside that envelope.

---

## Architecture: a multi-agent system

```
                ┌───────────────────────────────────────────┐
                │              AGENT (agent.py)              │
                │   reads account → scans chains → sizes     │
                └───────────────┬───────────────────────────┘
                                │
        IV-rank structure matrix (options.py) picks the *structure*
                                │
        ┌───────────────┬───────┴────────┬──────────────────┐
        ▼               ▼                ▼                  ▼
   BULL agent      BEAR agent       NEUTRAL agent     IV-RANK SCORER
   covered_call    protective_put   cash_secured_put  (chain IV percentile)
   (sell OTM call  (buy OTM put to  (sell OTM put     decides bull/bear/
    on held shares) cap drawdown,    on cash)         neutral path
                     optional collar)
        └───────────────┴───────┬────────┴──────────────────┘
                                │
                       ┌────────▼────────┐
                       │   RISK ARBITER  │  (agent.py RiskArbiter)
                       │  -2% position   │
                       │  -3% daily stop │  every proposal must pass
                       │  -8% drawdown   │
                       │  cash-secured   │
                       │  min OI/spread  │
                       └────────┬────────┘
                                │
                        ┌───────▼───────┐
                        │ CLIENT (MCP)  │  submit_order → Alpaca paper
                        │ SQLite log    │  decisions.db (audit trail)
                        └───────────────┘
```

### Strategy sub-agents (bull / bear / neutral)

| Agent | Strategy | When | Thesis |
|-------|----------|------|--------|
| **Bull** | `covered_call` — sell OTM call (~Δ0.25, ~21 DTE) on held shares | IVR high | harvest theta + vol premium on stock you already own |
| **Neutral/Income** | `cash_secured_put` — sell OTM put (~Δ0.25, ≤100% notional in cash) | IVR high | collect premium to buy the dip; fully cash-collateralized |
| **Bear/Hedge** | `protective_put` — buy OTM SPY put (+ optional collar) | IVR low | cap drawdown on the long book; collar funds the put → near-zero cost |

The **IV-rank structure matrix** picks which structure runs per underlying:
high IV → sell premium (bull/neutral), low IV → buy cheap protection (bear).

---

## Risk gates (non-negotiable, enforced by the arbiter)

| Gate | Value | Enforced by |
|------|-------|-------------|
| Position size | **≤ 2%** equity per trade | `RiskArbiter.check` + `size_contracts` |
| Daily loss circuit | **-3%** intraday → flatten, halt | `daily_loss_halted` |
| Drawdown pause | **-8%** from equity high → stop | `drawdown_pause_blocks` |
| Min open interest | **≥ 100** contracts | `passes_screen` |
| Max bid/ask spread | **≤ $0.15** | `passes_screen` |
| Net delta cap | **±0.30** portfolio | `net_delta` + arbiter |
| Options weight | ≤ **30%** of equity | `MAX_PORTFOLIO_WEIGHT_OPTIONS` |
| Cash reserve | keep **10%** buffer | `CASH_RESERVE_PCT` |

All risk params live in `config.RiskLimits` (dataclass) — tune in one place,
everything downstream honors it.

---

## Project layout

```
options/
├── options/
│   ├── config.py      # paper keys (env), options-level guard, risk params
│   ├── options.py     # Black-Scholes Greeks, /v2/options contract scan + filters
│   ├── strategies.py  # covered_call, cash_secured_put, protective_put/collar
│   ├── client.py      # MockClient (offline) + McpClient (real MCP, LIVE-gated)
│   ├── llm_referee.py # LLM risk referee (local Ollama, advisory)
│   └── agent.py       # decision loop, RiskArbiter, LLM referee, SQLite

├── tests/
│   └── test_options.py # 21 offline unit tests (Greeks, sizing, risk, spread)
└── README.md
```

### Components in detail

* **`config.py`** — reads `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` from env,
  verifies **options level ≥ 3**, refuses live mode, and centralizes all risk
  knobs.
* **`options.py`** — computes **Black-Scholes Greeks locally** (delta, gamma,
  theta, vega, rho) with **no external API**, solves implied vol by bisection,
  and filters contracts by OI / spread / DTE / IV rank.
* **`strategies.py`** — one clear function per paper-legal strategy; each
  returns a sized `OrderProposal` or `None`.
* **`agent.py`** — the loop: read account → scan SPY/QQQ chains → pick
  structure by IV rank → size at 2% → risk-gate → LLM referee review →
  submit via client → log to SQLite `decisions.db` with full reasoning.
* **`llm_referee.py`** — the LLM at the decision center. Every proposal the
  deterministic arbiter accepts is ALSO reviewed by a local LLM (Ollama;
  default `qwen2.5:1.5b` so it fits alongside prod services, override with
  `OLLAMA_MODEL`). The verdict + reasoning are written to the decision log.
  By default it is **advisory**: hard gates in code are the enforcement layer
  (local small models hallucinate numeric checks, so the LLM never holds sole
  authority over a real decision). Set `OLLAMA_REFEREE_ENFORCE=1` to let it
  veto. Fail-open on any outage — never stalls a cycle.
* **`client.py`** — a thin adapter. `MockClient` runs deterministic synthetic
  markets offline (no keys/network); `McpClient` talks to the REAL Alpaca MCP server
  (`uvx alpaca-mcp-server`, stdio JSON-RPC) gated behind
  `ALPACA_IS_LIVE=1`, with `ALPACA_PAPER=true` hard-forced in the server env.

---

## Running with paper keys

Set your **paper** (never live) keys and run the agent:

```bash
# 1. Offline self-test (no keys, no network)
cd options
python -m pytest tests -v                    # 50 tests, all offline

# 2. Sanity: import the whole package
python -c "import options.agent; print('ok')"

# 3. Live paper run (needs paper keys; MCP server pulled via `uvx`)
export ALPACA_API_KEY="PK…"                 # PowerShell: $env:ALPACA_API_KEY="…"
export ALPACA_SECRET_KEY="…"
export ALPACA_OPTIONS_LEVEL=3               # required
# leave ALPACA_IS_LIVE unset (0) → uses MockClient dry-run first
python -c "from options.agent import Agent; a=Agent(); print(a.run_cycle())"

# 4. Full live via MCP (only after you're sure of paper fills)
#    export ALPACA_IS_LIVE=1   → McpClient talks to `uvx alpaca-mcp-server`
#    (paper forced: the server env always gets ALPACA_PAPER=true)
```

`decisions.db` is written to the working directory — every trade, rejection,
and account snapshot is timestamped with reasoning for the P&L story.

> **Safety rail:** `config.validate_paper_config()` refuses `ALPACA_IS_LIVE=1`
> unless you explicitly re-enable it — the hackathon is paper-only.

---

## Verifying the build

```bash
cd C:\Users\Tench\.openclaw\workspace\alpaca-hackathon\options
python -m pytest -q                       # → 36 passed (offline)
python -c "import options.agent; print('import ok')"
```

The unit suite verifies (zero network):
* **Greeks** — BS ATM call price, put-call parity (price + delta), IV recovery.
* **Sizing** — never exceeds 2% equity; respects explicit dollar cap.
* **Risk arbiter** — −8% drawdown blocks, CSP needs full cash cover, oversized
  notional rejected, −3% daily loss trips flatten.
* **Spread/OI** — rejects contracts wider than $0.15 or below 100 OI.

---

## Options thesis (for the judges)

1. **Trade the volatility risk premium** — sell premium when IV rank is high,
   buy cheap protection when IV is low.
2. **Define risk** — every structure has capped max loss (covered call = stock
   assigned; CSP = cash-collateralized; protective put = collared).
3. **Harvest theta** — target ~21 DTE for the best decay-to-risk ratio.
4. **Auditable P&L** — every decision persisted with reasoning; the arbiter's
   rejections are as important as the fills.

Built paper-only, strictly Level-3-legal, tested offline (50 tests incl.
MCP contract suite + LLM referee), ready to go live against the real Alpaca
MCP server.
