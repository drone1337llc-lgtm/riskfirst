# VOLTAIR — PITCH

*A 2-minute read for a judge. Sharp, confident, specific. Every claim is built and tested.*

---

## What it is

VOLTAIR is an **autonomous AI options agent** for Alpaca paper trading. It's a multi-agent system — bull, bear, and neutral sub-agents debate the market, an LLM-backed risk arbiter referees, and an IV-rank scorer picks the options structure. It trades covered calls, cash-secured puts, and protective-put/collar hedges — strictly Level-3-legal, **no naked shorts** — through the Alpaca MCP server, with every decision logged to SQLite.

## Why this is an *agent*, not a script

A script has one rule. VOLTAIR has a **debate**:

- **Bull** proposes covered calls (sell ~Δ0.25 calls, ~21 DTE) to harvest theta + vol premium on shares it already owns.
- **Bear** proposes a protective put / credit collar — cheap downside protection when IV is low.
- **Neutral** proposes a cash-secured put — collect premium to buy the dip, fully cash-collateralized.
- **IV-Rank scorer** decides which path: **high IVR → sell premium; low IVR → buy protection.**
- **Risk arbiter** gates *every* proposal. Rejections are recorded as loudly as fills.

That's reasoning about market conditions, not a hardcoded trigger. It's what separates an agent from a bot.

## How it reasons + uses Alpaca

- **Black-Scholes Greeks computed locally** (delta/gamma/theta/vega/rho), implied vol solved by bisection — no external pricing API. **Verified by put-call parity tests.**
- **Reads live chains** via the Alpaca MCP server, picks structure by IV rank, sizes at ≤2% equity.
- **Fully offline-tested** against a deterministic mock client — 77 passing unit tests (Greeks, parity, IV recovery, sizing, drawdown blocks, spread/OI screens, MCP contract, LLM referee). Zero keys needed.

## The risk framework

| Gate | Value |
|------|-------|
| Position size | ≤ 2% equity |
| Daily loss circuit | −3% → flatten + halt |
| Drawdown pause | −8% → stop |
| Min OI / max spread | ≥100 / ≤$0.15 |
| Net delta / options weight / cash | ±0.30 / ≤30% / 10% buffer |

## The P&L story

The momentum core (Cryptonaut) was diagnosed to **three real loss drivers** — train↔live simulation mismatch, long-only with no walk-forward validation, and a macro gate that added no edge. It was then gated behind a **walk-forward out-of-sample evaluator that showed positive OOS Sharpe** — the same discipline now governs VOLTAIR: **we don't claim an edge we haven't validated OOS.** The paper track record is measured, not manufactured.

## Why we win

- **Options are the core instrument** (mandatory) ✓
- **Trades via Alpaca MCP** (mandatory) ✓
- **Multi-agent LLM reasoning + IV-rank structure selection** (creativity) ✓
- **Strict, quantified risk gates** (responsibility) ✓
- **77 passing offline tests + positive OOS Sharpe** (technical credibility) ✓
- **Auditable SQLite decision log** (explainability) ✓

**VOLTAIR — debate the market, define the risk, harvest the premium.**
