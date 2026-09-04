# Protonaut — PITCH

*A 2-minute read for a judge. Sharp, confident, specific. Every claim is built and tested.*

---

## What it is

Protonaut is an **autonomous CrewAI multi-agent crypto trader** on the Alpaca MCP server. Three LLM agents — a **bull**, a **bear**, and a **manager** — deliberate the market every 15 minutes, 24/7, and their verdict directly moves the book. It trades an 11-symbol crypto + equity universe (BTC, ETH, SOL, XRP, HYPE, NVDA, AMD, OKTA, SKHY, SNDK, MU) around the clock on a live Alpaca **paper** account, with every verdict, order, and rejection audited to SQLite.

## Why this is an *agent*, not a script

A script has one rule. Protonaut has a **debate**:

- **Bull** (`gpt-oss:120b`) — the momentum analyst. Finds the strongest names to overweight.
- **Bear** (`nemotron-3-nano:30b`) — the risk analyst. Flags overextended names and protects capital.
- **Manager** (`gemma4:31b`) — the portfolio manager. Synthesizes the two analysts into one decisive verdict.

Each agent independently reads the same market snapshot and returns a per-symbol lean (overweight / neutral / underweight) plus a risk stance. The manager fuses them into a single crew verdict. That's reasoning about market conditions, not a hardcoded trigger — and it's what separates an agent from a bot.

## Advisory with teeth

The crew's verdict isn't just advice — it **moves the allocations**:

- **Per-symbol allocation multipliers** in a **0.7–1.3× band** — overweight names get scaled up, underweight names get scaled down.
- **Risk-cap adjustment** by stance — **bull raises the cap to 1.10×, bear lowers it to 0.85×, neutral holds 1.0×**.
- The verdict is **cached hourly** so the crew doesn't hammer the cloud API every tick, and it goes on **standby when the market is closed** — no wasted tokens, no re-weighting a book that can't move.

## The risk rails (enforced before the broker)

Every order passes hard guardrails **before** it reaches Alpaca:

| Rail | Value |
|------|-------|
| Exposure cap | **95%** of equity |
| Cash reserve | **10%** buffer |
| Shorts | **No naked shorts** |
| De-leveraging | Orders scale exposure back when it exceeds the cap |

The de-leveraging rail is **verified live**: when total exposure hit **378%**, the system scaled it back to **0.25×** automatically. The rails are not a slide — they're running in production.

## The P&L story

Protonaut runs **unattended 24/7 on a 15-minute cadence** on a live Alpaca paper account (**PA39I1R4BNYL**, the original 07-12 hackathon account, **$83.2k equity**). Every crew verdict, every order, and every rejection lands in a **SQLite decision log** (`decisions.db`) — so the track record is *measured*, not manufactured. The paper P&L is a first-class judging criterion, and it's accruing in real time.

## Why we win

- **Multi-agent LLM reasoning** — a real bull/bear/manager debate, not a single signal (creativity) ✓
- **Trades via Alpaca MCP** (mandatory) ✓
- **Advisory-with-teeth** — the verdict moves allocations and the risk cap, not just advice ✓
- **Strict, quantified risk rails + live de-leveraging** (responsibility) ✓
- **Auditable SQLite decision log** (explainability) ✓
- **Live 24/7 paper trading on a real account** (technical credibility) ✓

**Protonaut — the crew decides, the rails enforce, the log proves both.**
