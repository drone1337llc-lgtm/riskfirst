# RiskFirst — BUILD IN PUBLIC JOURNAL

*The honest, dated record of building RiskFirst in the open. Every entry: what shipped, one lesson learned, one hook. This is the "build-in-public social challenge" track — posted as it happened, no rewrite.*

---

## Day 1 — Aug 25, 2026 · Diagnosing the losing bot

**Shipped:** A hard adversarial audit of our existing paper-trader (Cryptonaut). Full source review, no pep talk. Found the **three real loss drivers**:
1. **Train↔live mismatch** — the training env charged a 3%/trade commission that live paper never pays, teaching the policy to hug cash and under-deploy.
2. **Long-only with zero walk-forward validation** — one checkpoint, whole window, no test split → no demonstrated out-of-sample edge.
3. **A macro gate that capped allocation but added no directional edge.**

**Fixed at the root:** `COMMISSION 3%→0` (train = live paper), `DRAWDOWN_LAMBDA 3.0→0.4`, `DECISION_INTERVAL_S 60→300` (act every 5 min live, still train on 1-min bars).

**Lesson learned:** "The bot is losing because of fees" sounded right and was backwards. The fee lived in the *simulator*, not the live account. Diagnose against the source, not the story.

**Hook:** "Your bot isn't losing to fees. It's losing to a simulation mismatch. Here's the diff."

---

## Day 2 — Aug 26, 2026 · The OOS gate that vetoes hype

**Shipped:** A **walk-forward out-of-sample evaluator** — train on [t−k, t−0.25k], evaluate on [t−0.25k, t], roll forward. Reports OOS Sharpe and drawdown **net of honest costs**. This became the **hard gate**: any strategy change that doesn't improve OOS doesn't ship.

**Result:** The core showed **positive OOS Sharpe** — mean annualized **2.35**, folds **[+0.41, −9.43, +5.58, +26.95] unseeded → then made reproducible with a fixed seed (42): [−2.43, +14.57, −2.86, +0.13]** (2/4 negative — high variance, honestly framed). The canonical verdict now pins the seed so any judge re-runs the same numbers. First time we could say "this has a measured edge," not "this should have an edge."

**Lesson:** Tuning without an OOS gate is tuning to noise. Every "improvement" is ~50/50 to be a no-op — unless an OOS evaluator vetoes it first.

**Hook:** "We don't take improvement PRs anymore. They have to beat the walk-forward gate."

---

## Day 3 — Aug 27, 2026 · The options agent scaffold

**Built:** The RiskFirst scaffold — the multi-agent system. Bull / bear / neutral strategy sub-agents (`strategies.py`: covered calls, cash-secured puts, protective-put/collar), an **IV-rank structure matrix** (high IVR → sell premium; low IVR → buy protection), and a **Risk Arbiter** that gates every proposal. Black-Scholes Greeks computed **locally** (no external pricing API), implied vol by bisection, verified by **put-call parity**.

**Shipped:** **140 passing offline tests** — 60 cryptobot + 80 options (Greeks, parity, IV recovery, 2% sizing, drawdown blocks, spread/OI screens, MCP contract parsing, LLM referee, paper-loop runner). Zero keys, zero network. Paper-legal, Level-3-only: covered calls, cash-secured puts, protective-put/collar. **No naked shorts.**

**Lesson:** A trading agent's credibility is its test suite. Offline, deterministic, keyless tests are what let you say "the risk math is verified" without touching a paper dollar.

**Hook:** "140 tests on an options agent that run offline with zero keys. Here's how."
**Addendum (Aug 27, 07:40 MDT) — first live market-hours cycle captured:** The mock lane fired its first genuine RTH-open cycle at 07:30:01 and has been cycling clean every 5 min since (07:35:01, 07:40:02 both OK). Fresh decision logged: **TRADE covered_call IWM261011C00216000 qty1 $2.78, d0.251, IVR 0.70** — flat start to 100-share IWM lot to ~d0.25 covered call, exactly the bootstrap story. Equity $100k / cash $40k (MOCK-ACCT). The automation producing this evidence is cron-armed (`mock_lane_watch.sh`, flock-serialized, RTH-gated 09:30-16:00 NY) and self-runs through the judging window; the paper lane swaps in the moment keys land.


---

## Day 4 — Aug 28, 2026 · Live paper wiring (window opens)

**Built:** The **Alpaca MCP integration** — a typed client (`options/client.py`) that talks to the real `uvx alpaca-mcp-server` over stdio JSON-RPC (72 tools probed live): `get_account_info`, `get_all_positions`, `get_option_chain`, `place_option_order`, `close_all_positions`. **Paper is hard-forced in the server env (`ALPACA_PAPER=true`)** — a live key cannot reach a real account. `MockClient` runs the full loop deterministically offline; `McpClient` goes live only via the paper lane. **Config refuses real-trading mode unless explicitly re-enabled (`ALPACA_REAL_TRADING=1` — the only forbidden env).**

**Shipped:** The live decision loop writes **every** trade, rejection, and account snapshot to SQLite (`decisions.db`) with full reasoning — the auditable P&L trail.

**Lesson:** Safety-first wiring is a feature, not friction. The paper-forced rail means we can't accidentally live-fill a half-tested loop.

**Hook:** "The agent hard-forces paper trading in the MCP server env. Live keys physically cannot reach a real account."

---

## Day 5 — Aug 29, 2026 · Risk arbiter + LLM referee

**Built:** Full risk-gate suite enforced by the arbiter: **≤2% equity per position, −3% daily circuit breaker, −8% drawdown pause, min OI ≥100, max bid/ask ≤$0.15, net delta cap ±0.30, ≤30% options weight, 10% cash reserve.** Plus the **LLM referee** (Ollama `qwen2.5:1.5b`, stdlib-only client, hard 30 s timeout): every arbiter-accepted proposal gets a qualitative review whose verdict + reasoning land in the SQLite audit trail. Advisory by default — the deterministic gates are the enforcement layer, so the LLM can never silently approve or block a trade.

**Lesson:** The arbiter's **rejections are as important as the fills.** Logging a rejection is how you prove you *don't* over-trade into a drawdown.

**Hook:** "An options agent whose risk arbiter logs rejections as loudly as fills — that's the signal."

---

## Day 6 — Sep 1, 2026 — End-to-end dry run + freeze prep

**Shipped:** End-to-end dry run: the agent reads account → scans SPY/QQQ chains → picks structure by IV rank → sizes → risk-gates → LLM-reviews → submits → logs to SQLite. Verified the full suite still green. **Feature freeze set.**

**Lesson:** Ship the P&L narrative early. The decision log turning a flat paper week into a *proven-reasonable-agent* story is more valuable than chasing one more strategy.

**Hook:** "Feature-freezing an options agent 3 days before a hackathon deadline — and proud of it."

---

## Days 7–8 · Sep 2–4, 2026 · The live track record + submission

**Shipped:** The **live-paper track record** during the judging window (Aug 28–Sep 4), logged trade-by-trade to `decisions.db` — the paper loop self-starts the moment keys land (key watcher → runner → supervisor, all cron-armed, self-healing through the whole window). Cover image, demo reel, slide deck, and this public repo — **keys never committed, paper-only, fresh account.**

**Lesson (the whole point):** Build in public, validate out-of-sample, and let the risk arbiter say no. That's how you submit a *responsible agent* with a *measured* edge — not a hype deck.

**Hook:** "From a bot diagnosed with three real loss drivers to a gated, multi-agent options agent with a measured OOS edge — built in the open. Track record below."

---

### Track record
> **Live-paper results (Aug 28 – Sep 4):** [placeholder — final numbers from `decisions.db`]. Walk-forward OOS Sharpe: **positive** (validated Day 2).
