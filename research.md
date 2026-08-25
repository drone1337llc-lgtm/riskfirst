# Alpaca AI Trading Agents Hackathon — Research Memo

**Deadline:** Sep 4 2026 15:00 UTC · **Prize:** $6k · **Track:** Options Alpha Agents
**Adapted for:** Surge's Cryptonaut paper trader → make it profitable + competitive.

---

## 0. Mission constraints that RE-SHAPE the plan (read first)

From the official rules (lablab.ai live page + the community "HACKATHON.md" recap):

1. **Options are MANDATORY.** A pure equity/crypto strategy does **not** qualify. Every strategy *must incorporate options trading.* The "Options Alpha Agents" main challenge explicitly wants options (tracks: Options Alpha, Volatility & Event, Hedging & Risk, Income & Portfolio Overlay).
2. **MCP server or CLI usage is MANDATORY.** The agent must trade through Alpaca's **MCP server** and/or **CLI** — not just raw REST/SDK calls. (Source: hackathon live page + jacedeno/thetaforge HACKATHON.md.)
3. **Paper only**, fresh account, **$100k start**, account ID in submission. P&L is a *first-class* judging criterion — the agent must trade live-paper during Aug 28–Sep 4 to build a track record.
4. **Options max at Level 3** in paper (enabled by default). Level 3 allows: covered calls, cash-secured puts, **buy** calls/puts, **buy** call/put spreads (debit spreads). It does **NOT** allow naked short calls/puts or short (credit) spread legs beyond covered/cash-secured. (Source: `docs.alpaca.markets/us/docs/options-trading`.)

> **Structural implication for Cryptonaut:** The current long-only crypto PPO bot is the *wrong weapon* for this specific contest because it (a) doesn't use options → fails a hard requirement, and (b) doesn't use MCP/CLI → fails a hard requirement. Keep the PPO core, but **wrap it in an options-aware multi-agent system** (see §2/§3). Crypto options do not exist on Alpaca (see §1), so options must live on **equities/ETFs**, while the crypto/equity spot book supplies the directional alpha + the underlying for option hedges.

---

## 1. CRYPTO UNIVERSE SELECTION

### Key structural facts (verified)
- **Alpaca crypto = SPOT ONLY.** No crypto options, no crypto derivatives/margin shorting. Options exist **only on US equities/ETFs** (the `/v2/options/contracts` universe is equity underlyings). So crypto is the *directional spot book*; options are an *equity-layer*.
- **Confirmed Alpaca spot crypto (Apr 2026):** BTC, ETH, LTC, BCH, LINK, DOGE, SHIB, and (May 2026 expansion) ADA, ONDO, ARBITRUM + ~8 more (11 added; Crowdfund Insider). **SOL status is NOT confirmed in the primary list** — the bot's current SOL leg needs a runtime asset check before relying on it. **Verify against `/v2/assets` at build time.**
- **Fees:** equities/options commission-free; crypto is the *only* charged class (small per-trade fee, widens as fraction of notional on small qty). This makes crypto churn expensive → **crypto interval must be raised** and turnover penalized (matches Cryptonaut fix).

### Ranking: volatility-for-edge vs. liquidity/fee cost (Aug 2026)

| Rank | Asset | Vol-for-edge | Liquidity | Fee drag | Notes / why |
|---|---|---|---|---|---|
| 1 | **ETH** | High | Deep | Low | Best vol/momentum-to-cost ratio; bot already knows it; deepest alt liquid spot. Keep as core. |
| 2 | **BTC** | Medium | Deepest | Low | Low beta but the "carrier" — best liquidity, cleanest fills, lowest slippage; anchor the book. |
| 3 | **DOGE** | Very high | High | Med | Memecoin = high realized vol + deep retail liquidity; great short-term mean-rev/vol alpha, but fee+spread drag higher — trade only at longer interval. |
| 4 | **LINK** | High | Good | Med | High-beta oracle coin; good for vol regime + event plays; decent liquidity. |
| 5 | **LTC** | Med | Good | Low | Calmer, cheaper to trade; use for capital rotation / spread diversification, not alpha. |
| 6 | **ADA** | High | Good | Med | New listing (May 2026) → strong vol/retail flows; good "event/vol" candidate. |
| 7 | (SOL)* | High | High | Low | *If confirmed via assets API — best high-vol major with real liquidity. Verify first. |
| — | **Equity ETF w/ options** (SPY, QQQ, plus MAG7) | — | — | $0 | **These are the ONLY instruments with options.** If you want hedging/income via Alpaca options, equities are where it happens. |

**Shortlist (3–5):**
- **Directional crypto spot (long/short via momentum/PPO):** `ETH`, `BTC`, `DOGE` (3 core) + `LINK` or `ADA` as the high-vol satellite.
- **Options-underlying equity sleeve:** `SPY` (index hedge, iron condor/collar), `QQQ` (tech beta), plus a high-beta name from the book's biggest long.

**Rationale:** BTC+ETH give the reliable, cheap-to-trade backbone for the directional alpha the bot already does; DOGE/LINK/ADA add the high-vol "edge fuel" that alpha needs, but only tradeable at longer intervals (60s → 15–60 min) to survive fees. The **real competitive edge is the equity options layer** layered on top — that's the mandatory box ticked and where the contest's scoring overlap lives.

---

## 2. OPTIONS ALPHA STRATEGIES (software-executable, Alpaca Level-3 compliant)

**All are paper-tradable and Level ≤3.** Data needed: option chain (`/v2/options/contracts`), real-time+historical option data, Greeks (compute locally via Black–Scholes — no external API needed — or pull snapshot), IV Rank from 52-week history.

### A. Covered Call Income (Level 1) — **PRIORITIZE (P1)**
- **Mechanics:** hold 100 shares of an ETF (SPY/QQQ) or high-beta name; sell OTM call (~2–5% above spot) ~21 DTE. Collect premium (theta). If called, profit = stock gain to strike + premium.
- **Why it generates P&L in paper:** steady theta income in flat/up markets; works 3 out of 4 regimes; *zero fee drag* (equities commission-free). Very judge-friendly ("income overlay").
- **Data needed:** chain scan, IV rank (sell only when IV above median), delta ~0.25–0.30.
- **Risk/complexity:** caps upside (forgone rallies), assignment handling (NTA poll). **Low complexity, high reliability.** Best first win.

### B. Cash-Secured Put (wheel entry) — Level 1 — **PRIORITIZE (P1)**
- **Mechanics:** sell OTM put (~delta 0.25, cash secured, ≤ 100% notional in cash), collect premium. If unassigned → keep theta profit. If assigned → you own the stock at a discount (reduces entry cost), then roll to covered call.
- **Why P&L in paper:** works in sideways/bullish; premium-rich in high-IV names; paired with a mean-reversion signal it "buys dips" cheaply. No options fee.
- **Data:** IV rank, support level for strike pick, cash/buying-power check.
- **Risk:** directional loss to downside if stock craters; cap size at 2% equity per trade. **Low-moderate.** Clean and automatable.

### C. Long Straddle / Strangle (event or volatility regime) — Level 2 — **PRIORITY (P2)**
- **Mechanics:** buy ATM call + put (straddle) or slightly OTM (strangle) around a **known catalyst** (earnings, CPI, Fed decision) or when realized vol is cheap vs IV (low IV rank) and a move is expected. Sell/exit at target.
- **P&L in paper:** captures direction+vol expansion; the event-date IV expansion alone can carry it even before price moves. Strong fit for the **"Volatility & Event"** track. Alpaca paper options are commission-free → break-even is just bid/ask spread.
- **Data:** event calendar, IV rank, realized/implied vol ratio.
- **Risk:** high theta decay if the move is small/delayed; buy only defined-odds. **Moderate risk.** Clean execution.

### D. Protective Put Hedge for the long book (incl. a credit collar) — Level 2/3 — **P2 (the "Hedging & Risk" track)**
- **Mechanics:** on the crypto/equity long book, buy an OTM put on an equity ETF proxy (or buy put on SPY) to cap drawdown; optionally sell an OTM call to fund it → **collar = net small credit**. The Mototown winning-pattern repo runs exactly this (Thesis Debate + Risk Arbiter + multi-leg hedges every 5 min).
- **Why P&L:** limits the long-only downside that currently bleeds Cryptonaut on crashes; keeps the PPO book green when momentum breaks. Judges read this as institutional-grade risk (scores "Technology" + "Hedging").
- **Data:** portfolio net delta, IV, spot.
- **Risk:** hedge cost (premium), slight drag; reduce via collar. **Low-moderate** (it's a loss-limited short).

**Recommendation for first cut:** **A (covered call) + B (cash-secured put)** as the *income engine* (both Level 1, simplest, highest hit-rate, all-weather) **+ D (protective put / collar)** as the *risk engine* for the long book. That trio covers 3 of the 4 contest tracks (Income, Hedging/Risk) with minimal complexity, zero naked risk, and a clean narrative. Add **C (long straddle)** as the **Volatility & Event** differentiator once the core is proven — it's the highest "alpha-flair" and creativity lever for judging.

**Implementation fit:** these are exactly what the two best-documented prior hackathon agents did — `subhu770/alpaca-options-agent` (debit spreads, 2%-of-equity risk, 50% profit/stop) and `Mototown/alpaca-trading-agent` (multi-agent hedge arbiter, Kelly sizing, IV-rank structure matrix, circuit breakers). Mirror their skeleton but add our PPO edge for timing.

---

## 3. COMPETITION JUDGING EDGE — what actually wins

**Judging criteria (official):** ① P&L performance ② Technology implementation ③ Creativity/originality ④ Presentation/execution (+ optional social engagement bonus).

### Highest-leverage things to nail (in order):
1. **Satisfy hard requirements FIRST** — options + MCP/CLI + fresh $100k paper + live trade the whole window. This is 40% of people auto-disqualified; being present with a *running* agent is a massive edge. Reusing an account = **ineligible**.
2. **P&L that you can show** — because it's first-class, **run live-paper from hour one** (not just at the end). Even a modest, real, logged return beats a hypothetical. Log every decision to SQLite + a dashboard (Mototown pattern).
3. **Architecture read as "autonomous AI agent," not a script** — a **multi-agent** design (sentiment/technical/risk + an orchestrator/arbiter) with **LLM reasoning** about *why* a trade is taken. Judges reward agency. The bar in prior winners: bull/bear/neutral sub-agents + risk arbiter + guardrails + circuit breakers.
4. **Show risk gates explicitly** — position sizing (≤2% equity/trade), max exposure, daily loss circuit breaker (−3%), drawdown pause (−8%), min OI (100), max bid/ask ($0.15), net-delta cap (±0.30). This is how you distinguish "trading bot" from "responsible agent."
5. **A tight, real narrative** — one-page write-up (AI logic + risk gates + Alpaca infra) + demo video + slides. Judges score *explainability* of the strategy and the reasoning behind results. A clear options thesis ("income via covered calls, hedged long book") scores higher than a vague "momentum."

### What winning Alpaca/lablab trading-agent submissions include (patterns from prior submissions/repos):
- **Options as the core instrument** (debit spreads, income/hedging) — never a crypto/equity-only bot.
- **Multi-agent / thesis-debate** architecture with an LLM arbiter deciding between directions.
- **IV-rank-driven structure selection** (their market-condition → structure matrix is a strong, judge-visible differentiator).
- **Real infra chops:** MCP server integration (Dockerized `ghcr.io/alpacahq/alpaca-mcp`), typed wrappers, a live dashboard, SQLite decision logs, **unit tests on Greeks/sizing/guardrails** (offline, no keys).
- **Strict, quantified risk management** presented explicitly.
- **A proven, reproducible backtest** + short DTL of edge (days to milestones in the README).

### Biggest mistakes to avoid:
- Not trading the fresh account during the live window (no P&L to show).
- Raw-REST-only (fails MCP/CLI requirement).
- Options-less (fails core requirement).
- Unclear/under-hedged sizing that blows the $100k (a hard "P&L" miss).
- A bot that only goes long in a drawdown week (the fee-bleed trap Cryptonaut currently sits in).

**Recommendation for Cryptonaut adaptation:** Keep the PPO momentum signal for the **long spot/crypto book** (raise interval → 15–60 min, add turnover penalty, add downside capture). Layer on the **equity options income engine** (covered calls + cash-secured puts on SPY/QQQ/high-beta names) and a **protective-put/collar hedge** for the long book, driven through **Alpaca's MCP server**, with a multi-agent (bull/bear/neutral + risk arbiter) LLM layer on top for the "autonomous agent" story. Ship the dashboard, tests, and a crisp narrative. This hits every requirement + 4 of 4 tracks.

---

### Sources
- lablab.ai official hackathon page + `live` variant (rules, judging, prizes, MCP/CLI requirement, fresh-account rule). https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon
- Community rules recap (options-mandatory, fresh $100k account, deliverables). https://github.com/jacedeno/thetaforge/blob/main/HACKATHON.md
- Alpaca Options Trading docs (Levels 0–3, contracts endpoint, paper defaults, MLEG, exercise/assignment). https://docs.alpaca.markets/us/docs/options-trading
- Alpaca crypto (spot only, fees, supported list). https://docs.alpaca.markets/us/docs/crypto-trading · https://alpaca.markets/crypto · https://alpaca.markets/support/what-cryptocurrencies-does-alpaca-currently-support
- Alpaca May-2026 crypto expansion (ADA, ONDO, ARB + others). https://www.crowdfundinsider.com/2026/05/280485-alpaca-expands-crypto-portfolio-with-cardano-ondo-arbitrum-other-digital-assets/
- Prior-participant winning patterns: https://github.com/subhu770/alpaca-options-agent · https://github.com/Mototown/alpaca-trading-agent
- Volatility context (Aug 2026): https://coincodex.com/most-volatile/ · https://www.analyticsinsight.net/cryptocurrency-analytics-insight/best-high-volatility-crypto-coins-for-trading-in-2026

*Note: live crypto list and per-token fee tables are subject to change — verify against `/v2/assets` at build time.*
