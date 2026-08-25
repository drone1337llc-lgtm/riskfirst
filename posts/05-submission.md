# Post 5 — Submission (Sep 3)

** Heres what we shipped, and where its honestly weak.**

**RiskFirst** — an options & equities agent on Alpaca MCP with a walk-forward OOS gate.

What shipped:
- Options/equities lane: vol-targeted equity sizing, options wheel overlay, guardrails (≤4 legs, /leg,  min, pre-broker intent validation)
- MCP route: stdio/http/sse via uvx alpaca-mcp-server
- Crypto secondary lane with a **spec-compliant OOS verdict**: mean Sharpe 5.88, but 1/4 folds negative — demoted, honestly
- Risk rails: −10% DD circuit-breaker, flat-on-trip
- Full repo, this deck, and a paper account ID (below)

Where it's honestly weak:
- Crypto lane high variance — that's why it's secondary
- Live paper verification pending (keys → live data → a real paper multi-leg order → video)
- 1-min decision bars: tuned for the hackathon window, not for week-long holds

**Paper account ID:** PENDING — keys requested, the moment they land this gets a real number and a real order.

Repo: (public link here once Surge green-lights the push)
