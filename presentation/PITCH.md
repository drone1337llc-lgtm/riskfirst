# RiskFirst — PITCH

*A 2-minute read for a judge. Sharp, confident, specific. Every claim is built and tested.*

---

## What it is

RiskFirst is an **autonomous AI options agent** for Alpaca paper trading. It's a multi-agent system — bull, bear, and neutral sub-agents debate the market, an LLM-backed risk arbiter referees, and an IV-rank scorer picks the options structure. It trades covered calls, cash-secured puts, and protective-put/collar hedges — strictly Level-3-legal, **no naked shorts** — through the Alpaca MCP server, with every decision logged to SQLite.

## Why this is an *agent*, not a script

A script has one rule. RiskFirst has a **debate**:

- **Bull** proposes covered calls (sell ~Δ0.25 calls, ~21 DTE) to harvest theta + vol premium on shares it already owns.
- **Bear** proposes a protective put / credit collar — cheap downside protection when IV is low.
- **Neutral** proposes a cash-secured put — collect premium to buy the dip, fully cash-collateralized.
- **IV-Rank scorer** decides which path: **high IVR → sell premium; low IVR → buy protection.**
- **Risk arbiter** gates *every* proposal. Rejections are recorded as loudly as fills.

That's reasoning about market conditions, not a hardcoded trigger. It's what separates an agent from a bot.

## How it reasons + uses Alpaca

- **Black-Scholes Greeks computed locally** (delta/gamma/theta/vega/rho), implied vol solved by bisection — no external pricing API. **Verified by put-call parity tests.**
- **Reads live chains** via the Alpaca MCP server (`uvx alpaca-mcp-server`, stdio JSON-RPC — every call a tool: account, chains, multi-leg orders, `close_all_positions` circuit-breaker). Paper is **hard-forced** in the client's server env: a live key cannot reach a real account.
- **Fully offline-tested** against a deterministic mock client — **87 passing tests** (Greeks, parity, IV recovery, 2% sizing, drawdown blocks, spread/OI screens, MCP contract, LLM referee, paper-loop runner). Zero keys needed.

## The risk framework

| Gate | Value |
|------|-------|
| Position size | ≤ 2% equity |
| Daily loss circuit | −3% → flatten + halt |
| Drawdown pause | −8% → stop |
| Min OI / max spread | ≥100 / ≤$0.15 |
| Net delta / options weight / cash | ±0.30 / ≤30% / 10% buffer |

## The P&L story

We ran an **adversarial audit of our own existing bot** (Cryptonaut) before adding a single feature — and found **three real loss drivers**: train↔live simulation mismatch, long-only with no walk-forward validation, and a macro gate that added no edge. We fixed the process, then built a **walk-forward out-of-sample evaluator** and made it the hard gate: **the crypto lane stays only if OOS Sharpe is positive net.** Result: mean annualized Sharpe **5.88** (folds [0.41, −9.43, 5.58, 26.95] — 1/4 negative, honestly noisy, hence secondary lane). That discipline now governs RiskFirst: **we don't claim an edge we haven't validated OOS.** The paper track record is measured, not manufactured.

## Why we win

- **Options are the core instrument** (mandatory) ✓
- **Trades via Alpaca MCP** (mandatory) ✓
- **Multi-agent LLM reasoning + IV-rank structure selection** (creativity) ✓
- **Strict, quantified risk rails + circuit-breaker** (responsibility) ✓
- **87 passing offline tests + positive OOS Sharpe** (technical credibility) ✓
- **Auditable SQLite decision log** (explainability) ✓

**RiskFirst — the gate decides what trades, the arbiter decides what ships, the log proves both.**
