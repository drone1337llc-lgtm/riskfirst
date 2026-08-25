"""Equities + options agent scaffold for the Alpaca AI Trading Agents hackathon.

Re-scope per alpaca-hack-verdict.md (2026-08-24): the crypto-only PPO lane is a
requirements mismatch. This module is the OPTIONS + EQUITIES lane on Alpaca PAPER,
reusing the champion/challenger + circuit-breaker patterns from the crypto lane.

Design (v0):
  - Equities leg: momentum/mean-reversion signal from stock bars (intraday),
    sized via simple vol-targeting; orders through TradingClient (paper).
  - Options leg: cash-secured put / covered call wheel on liquid underlyings,
    same guardrail philosophy as the crypto lane:
      * only paper, ALPACA_PAPER asserted
      * notional caps + min order floors
      * circuit breaker: realized drawdown or OOS gate fail -> halt lane
  - LLM loop (Ollama) decides between lane proposals; executor enforces caps.

Verified against alpaca-py 0.43.5 (2026-08-24):
  - multi-leg option orders = OrderRequest(order_class="mleg", legs=[OptionLegRequest],
    position_intent=PositionIntent.BUY_TO_OPEN|BUY_TO_CLOSE|SELL_TO_OPEN|SELL_TO_CLOSE);
    at most 4 legs, all unique symbols. OptionLegRequest side = 'buy'|'sell'.
  - option chain/bars via OptionHistoricalDataClient (public data, no keys).

Standing rule: NEVER submit to live endpoints. assert config.ALPACA_PAPER.
"""
from __future__ import annotations

import logging

from alpaca.data.historical import StockHistoricalDataClient, OptionHistoricalDataClient
from alpaca.data.requests import OptionChainRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderClass, OrderType, PositionIntent, TimeInForce
from alpaca.trading.requests import (
    MarketOrderRequest,
    OptionLegRequest,
    OrderRequest,
)

import config

log = logging.getLogger("equity_agent")

assert config.ALPACA_PAPER, "Refusing to construct equities/options agent without paper mode."

# Option underlyings we may trade (liquid, weekly chains). Start small.
EQUITY_UNIVERSE = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]

# Hard risk rails (reuse crypto-lane discipline, tuned for equities).
MAX_OPTION_NOTIONAL = 500.0        # per leg, paper
MIN_ORDER_NOTIONAL = 1.0
CIRCUIT_BREAKER_DD = 0.10         # -10% equity curve halt
MAX_OPTION_DELTA_EXPOSURE = 0.15  # cap aggregate delta exposure of option book

# Friendly intent codes -> PositionIntent enum names.
_POS_INTENT = {
    "bto": "BUY_TO_OPEN",
    "btc": "BUY_TO_CLOSE",
    "sto": "SELL_TO_OPEN",
    "stc": "SELL_TO_CLOSE",
}


def equity_bars(symbol: str, lookback: int = 390):
    """1-min bars for an equity symbol (public data, no keys needed)."""
    from datetime import datetime, timedelta, timezone

    from alpaca.data.requests import StockBarsRequest

    client = StockHistoricalDataClient()
    req = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame(1, TimeFrameUnit.Minute),
        start=datetime.now(timezone.utc) - timedelta(minutes=lookback + 15),
    )
    df = client.get_stock_bars(req).df
    df = df.xs(symbol, level="symbol") if "symbol" in df.index.names else df
    return df[["open", "high", "low", "close", "volume"]].tail(lookback)


def option_chain(underlying: str) -> list[dict]:
    """Latest option chain for one underlying (public data)."""
    client = OptionHistoricalDataClient()
    try:
        chain = client.get_option_chain(OptionChainRequest(symbol=underlying))
    except Exception as exc:
        log.warning("chain unavailable for %s: %s", underlying, exc)
        return []
    out = []
    for c in chain:
        out.append({
            "symbol": c.symbol,
            "type": c.type,
            "strike": float(c.strike_price),
            "exp": str(c.expiration_date),
            "bid": float(c.bid or 0.0),
            "ask": float(c.ask or 0.0),
            "open_interest": int(c.open_interest or 0),
        })
    return out


def submit_multi_leg(legs: list[dict], intent: str) -> dict:
    """Submit a multi-leg paper option order (wheel: CSP / credit spread).

    legs: [{symbol, qty, side, premium}] where side is 'buy'|'sell';
          qty is the leg ratio (maps to OptionLegRequest.ratio_qty).
    intent: 'bto'|'btc'|'sto'|'stc'.
    ENFORCES per-leg notional cap before submit.
    """
    if not (2 <= len(legs) <= 4):
        return {"error": "leg_count", "detail": "mleg requires 2..4 legs"}
    if len({l["symbol"] for l in legs}) != len(legs):
        return {"error": "dup_symbol", "detail": "all legs must have unique symbols"}
    if not isinstance(intent, str) or intent.lower() not in _POS_INTENT:
        return {"error": "bad_intent", "detail": "use bto|btc|sto|stc"}
    req_legs = [
        OptionLegRequest(
            symbol=leg["symbol"],
            ratio_qty=leg["qty"],   # alpaca-py 0.43.5: ratio_qty (not qty) is the required leg field
            side=leg["side"],
        )
        for leg in legs
    ]
    for leg in legs:
        notional = abs(leg["qty"]) * leg.get("premium", 0.0)
        if notional > MAX_OPTION_NOTIONAL:
            log.warning("leg %s notional %.2f exceeds cap %.2f; refusing order",
                        leg["symbol"], notional, MAX_OPTION_NOTIONAL)
            return {"error": "notional_cap", "leg": leg["symbol"]}
    client = TradingClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, paper=True)
    try:
        order = OrderRequest(
            symbol=legs[0]["symbol"],
            order_class=OrderClass.MLEG,
            type=OrderType.MARKET,  # paper mleg: market fills, guards on notional + legs
            qty=1,                  # contract count; leg ratios below scale relative to it
            legs=req_legs,
            position_intent=PositionIntent[_POS_INTENT[intent.lower()]],
            time_in_force=TimeInForce.DAY,
        )
        resp = client.submit_order(order)
    except Exception as exc:
        log.error("option order submit failed: %s", exc)
        return {"error": "submit", "detail": str(exc)}
    return {"order_id": str(resp.id), "status": resp.status, "legs": len(legs)}
