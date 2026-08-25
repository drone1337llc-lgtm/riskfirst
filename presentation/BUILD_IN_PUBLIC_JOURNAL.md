# VOLTAIR — BUILD IN PUBLIC JOURNAL

*The honest, dated record of building VOLTAIR in the open. Every entry: what shipped, one lesson learned, one hook. This is the "build-in-public social challenge" track — posted as it happened, no rewrite.*

---

## Day 1 — Aug 25, 2026 · Diagnosing the losing bot

**Shipped:** A hard adversarial audit of our existing paper-trader (Cryptonaut). Full source review, no pep talk. Found the **three real loss drivers**:
1. **Train↔live mismatch** — the training env charged a 3%/trade commission that live paper never pays, teaching the policy to hug cash and under-deploy.
2. **Long-only with zero walk-forward validation** — one checkpoint, whole window, no test split → no demonstrated out-of-sample edge.
3. **A macro gate that capped allocation but added no directional edge.**

**Lesson learned:** "The bot is losing because of fees" sounded right and was backwards. The fee lived in the *simulator*, not the live account. Diagnose against the source, not the story.

**Hook:** "Your bot isn't losing to fees. It's losing to a simulation mismatch. Here's the diff."

---

## Day 2 — Aug 26, 2026 · The OOS gate that vetoes hype

**Shipped:** A **walk-forward out-of-sample evaluator** — train on [t−k, t−0.25k], evaluate on [t−0.25k, t], roll forward. Reports OOS Sharpe and drawdown **net of honest costs**. This became the **hard gate**: any proposed fix that doesn't improve OOS doesn't ship.

**Result:** The core showed **positive OOS Sharpe**. First time we could say "this has a measured edge," not "this should have an edge."

**Lesson learned:** Tuning without an OOS gate is tuning to noise. Every "improvement" is ~50/50 to be a no-op — unless an OOS evaluator vetoes it first.

**Hook:** "We don't take improvement PRs anymore. They have to beat the walk-forward gate."

---

## Day 3 — Aug 27, 2026 · The options agent scaffold

**Built:** The VOLTAIR scaffold — the multi-agent system. Bull / bear / neutral strategy sub-agents, an **IV-rank structure matrix** (high IVR → sell premium; low IVR → buy protection), and a **Risk Arbiter** that gates every idea. Black-Scholes Greeks computed **locally** (no external pricing API), implied vol by bisection, verified by **put-call parity**.

**Shipped:** **50 passing offline unit tests** — Greeks, parity, IV recovery, 2% sizing, drawdown blocks, spread/OI screens, MCP contract parsing, and the LLM referee. Zero keys, zero network. Paper-legal, Level-3-only: covered calls, cash-secured puts, protective-put/collar. **No naked shorts.**

**Lesson learned:** A trading agent's credibility is its test suite. Offline, deterministic, keyless tests are what let you say "the risk math is verified" without touching a paper dollar.

**Hook:** "77 tests on an options agent (27 cryptobot + 50 options incl. MCP contract + LLM referee) that run offline with zero keys. Here's how."

---

## Day 4 — Aug 28, 2026 · Live paper wiring (window opens)

**Built:** The **Alpaca MCP integration** — a typed wrapper (`client.py`) that talks to the Dockerized `ghcr.io/alpacahq/alpaca-mcp`, reads `/v2/options/contracts` chains, and submits orders to a **fresh paper account** (the one required by the rules). `MockClient` runs the full loop deterministically offline; `McpClient` goes live behind a `LIVE` flag. **Config refuses live mode unless explicitly re-enabled.**

**Shipped:** The live decision loop writes **every** trade, rejection, and account snapshot to SQLite (`decisions.db`) with full reasoning — the auditable P&L trail.

**Lesson learned:** Safety-first wiring is a feature, not friction. The `ALPACA_IS_LIVE=1` refuse-by-default rail means we can't accidentally paper-fill a half-tested loop.

**Hook:** "The agent refuses to go live unless you explicitly tell it to. That's the only way to ship a paper bot."

---

## Day 5 — Aug 29, 2026 · Risk arbiter hardening

**Built:** Full risk-gate suite enforced by the arbiter: **≤2% equity per position, −3% daily circuit breaker, −8% drawdown pause, min OI ≥100, max bid/ask ≤$0.15, net delta cap ±0.30, ≤30% options weight, 10% cash reserve.**

**Lesson learned:** The arbiter's **rejections are as important as the fills.** In a paper bot, the discipline is the P&L story. Logging a rejection is how you prove you *don't* over-trade into a drawdown.

**Hook:** "An options bot whose risk arbiter logs more rejections than fills — that's the signal."

---

## Day 6 — Sep 1, 2026 — End-to-end dry run + freeze prep

**Shipped:** End-to-end dry run: the agent reads account → scans SPY/QQQ chains → picks structure by IV rank → sizes → risk-gates → submits → logs to SQLite. Verified the 21-test suite still green. **Feature freeze set.**

**Lesson learned:** Ship the P&L narrative early. The decision log turning a flat paper week into a *proven-reasonable-agent* story is more valuable than chasing one more strategy.

**Hook:** "Feature-freezing an options agent 3 days before a hackathon deadline — and proud of it."

---

## Days 7–8 · Sep 2–4, 2026 · The live track record + submission

**Shipped:** The **live-paper track record** during the judging window (Aug 28–Sep 4), logged trade-by-trade to `decisions.db`. Cover image, demo video, slide deck, and this public repo — **keys never committed, paper-only, fresh account.**

**Lesson learned (the whole point):** Build in public, validate out-of-sample, and let the risk arbiter say no. That's how you submit a *responsible agent* with a *measured* edge — not a hype deck.

**Hook:** "From a bot diagnosed with three real loss drivers to a gated, multi-agent options agent with a measured OOS edge — 11 days, built in the open. Track record below."

---

### Track record
> **Live-paper results (Aug 28 – Sep 4):** [placeholder — final numbers from `decisions.db`]. Walk-forward OOS Sharpe: **positive** (validated Day 2).
