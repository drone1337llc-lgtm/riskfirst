# Post 3 — The MCP Lane (Aug 30)

** Agent meets Alpaca MCP: the options/equities lane lives in tool space.**

The MCP route is live (uvx alpaca-mcp-server, stdio/http/sse, in/run_mcp.sh). The agent doesn't fake orders — it talks to Alpaca through typed tools, the same ones a human CLI user would.

Guardrails aren't vibes, they're pre-broker checks:
- **≤4 unique legs** per multi-leg order (Alpaca hard rule, enforced before submission)
- **/leg notional cap** — no yoloing the paper account
- ** minimum** — no dust orders
- **Position intent validation** — BTO/BTC/STO/STC must be coherent before the broker sees it
- **−10% drawdown circuit-breaker** — the book goes flat, full stop

Everything is smoke-tested pre-broker (leg-count and bad-intent requests rejected in tests, never reaching the API).

Equity/options data + orders need paper API keys — which means this post's demo video is pending one thing: a paper account. The code is written, tested, and staged.
