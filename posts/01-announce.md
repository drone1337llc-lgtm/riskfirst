# Post 1 — Announce (Aug 27)

**I adversarial-reviewed my own trading bot and found it was built on a wrong assumption.**

Entering the Alpaca AI Trading Agents hackathon, I thought I had a finished crypto bot. Then I ran an adversarial council review on myself and it fell apart — the requirements had changed under me. The hackathon's real tracks are **options + equities + MCP/CLI agents**, not crypto PPO.

So I re-scoped. Meet **RiskFirst**: an options & equities agent on the Alpaca MCP, with a walk-forward out-of-sample gate as the price of admission.

First, three foundation fixes my review forced:
- **Commission 3% → 0** (train == live paper, no fiction)
- **Drawdown lambda 3.0 → 0.4** (reward risk-taking properly)
- **Decision interval 60s → 300s** (trade like a portfolio manager, not a scalper)

Also fixed a silent killer: a 0-commission sim that cancelled *every order* (tensortrade patched, verified zero cancels). Without that fix, the honest config would have just hugged cash.

Repo goes public this week. Gate results next post.
