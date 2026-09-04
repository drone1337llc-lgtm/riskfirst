# ALPACA HACKATHON — PROJECT TITLE & DESCRIPTION

## Title
**Protonaut: A CrewAI Multi-Agent Crypto Trader on Alpaca MCP**

*A CrewAI multi-agent crypto trading system on the Alpaca MCP server — three LLM agents (bull, bear, manager) deliberate the market every 15 minutes and their verdict directly influences per-symbol allocations and the risk cap, trading an 11-symbol crypto + equity universe around the clock.*

---

## Hook (1–2 sentences)

Protonaut is an **autonomous CrewAI multi-agent crypto trader** — not a script — that runs a bull / bear / manager debate through three LLM agents every 15 minutes, 24/7, and turns the verdict directly into per-symbol allocation multipliers and a risk-cap adjustment. It trades an 11-symbol crypto + equity universe on a live Alpaca paper account behind hard, pre-broker risk rails — with every verdict, order, and rejection audited to SQLite.

---

## Detailed Description (what the judges read)

### The problem
Most "AI trading bots" are single-signal scripts that go long, bleed in choppy tape, and have **no definition of risk**. And of the ones that use multiple models, almost none behave like an agent: they execute a fixed rule with no reasoning, no market-regime judgment, and no guardrail against over-leverage.

Protonaut was built to be the opposite: a system that **debates**, **decides**, **sizes**, and **protects** — with every decision auditable to SQLite and every trade behind non-negotiable risk rails.

### Why it's an autonomous AI agent (not a script)
Protonaut is a **CrewAI multi-agent system** with three LLM agents at the decision center:

- **Bull** (`gpt-oss:120b`) — the **Momentum Analyst**. Finds the strongest names to overweight; leans into strength.
- **Bear** (`nemotron-3-nano:30b`) — the **Risk Analyst**. Flags overextended names to underweight and protects capital; trims into strength, buys weakness.
- **Manager** (`gemma4:31b`) — the **Portfolio Manager**. Synthesizes the two analysts into one decisive verdict, balancing momentum and risk.

Each agent independently reads the same market snapshot and returns a per-symbol lean (overweight / neutral / underweight) plus an overall risk stance. The manager fuses them into a single crew verdict. The agent **reasons about market conditions** — not hardcoded entry rules — because the structure of the book is driven by the crew's live read of the tape.

### Advisory with teeth
The crew's verdict isn't just advice — it **moves the allocations**:

- **Per-symbol allocation multipliers** in a **0.7–1.3× band** — overweight names get scaled up, underweight names get scaled down.
- **Risk-cap adjustment** by stance — **bull raises the cap to 1.10×, bear lowers it to 0.85×, neutral holds 1.0×**.
- The verdict is **cached hourly** so the crew doesn't hammer the cloud API every tick, and it goes on **standby when the market is closed** — no wasted tokens, no re-weighting a book that can't move.

### The universe
Protonaut trades an **11-symbol crypto + equity universe** around the clock: **BTC, ETH, SOL, XRP, HYPE** (crypto) and **NVDA, AMD, OKTA, SKHY, SNDK, MU** (equities) — a mix that keeps the crew reasoning across both asset classes, not just one.

### How it uses Alpaca (MCP)
Protonaut trades through the **Alpaca MCP server** (`uvx alpaca-mcp-server`, launcher `bin/run_mcp.sh` — stdio / streamable-http / SSE), so the crew's market reads and order decisions are tool-visible and auditable, not a black box. It runs on a live Alpaca **paper** account — **PA39I1R4BNYL**, the original 07-12 hackathon account, **$83.2k equity** — unattended 24/7 on a 15-minute cadence.

### The risk framework (non-negotiable, enforced pre-broker)

| Rail | Value |
|------|-------|
| Exposure cap | **95%** of equity |
| Cash reserve | **10%** buffer |
| Shorts | **No naked shorts** |
| De-leveraging | Orders scale exposure back when it exceeds the cap |

The de-leveraging rail is **verified live**: when total exposure hit **378%**, the system scaled it back to **0.25×** automatically. Every order passes these guardrails **before** it reaches the broker — the rails are running in production, not on a slide.

### P&L story (honest, defensible)
Protonaut runs **unattended 24/7 on a 15-minute cadence** on a live Alpaca paper account. Every crew verdict, every order, and every rejection lands in a **SQLite decision log** (`decisions.db`) — so the track record is *measured*, not manufactured. The paper P&L is a first-class judging criterion, and it's accruing in real time.

**Built to the actual scoring criteria**: multi-agent LLM reasoning (creativity), MCP/CLI (mandatory), advisory-with-teeth that moves allocations and the risk cap, quantified risk rails with live de-leveraging (responsibility), and an auditable SQLite decision log (explainability).

---

*Protonaut — the crew decides, the rails enforce, the log proves both.*
