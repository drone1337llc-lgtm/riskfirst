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
MAX_OPTION_DELTA_EXPOSURE = 0.30  # cap aggregate delta exposure of option book

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


def demo_bars(symbol: str, lookback: int = 390):
    """Key-free 5-min bars via yfinance (demo only; Alpaca stock bars need keys)."""
    import yfinance as yf

    df = yf.Ticker(symbol).history(period="5d", interval="5m")
    if df is None or df.empty:
        return df
    df = df[["Open", "High", "Low", "Close", "Volume"]].rename(
        columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}
    )
    return df.tail(lookback)


def demo_chain(underlying: str, spot: float) -> list[dict]:
    """Synthetic option chain around spot for the key-free demo.

    Real Alpaca chains need credentials; this is clearly-labeled illustrative
    data so the demo can exercise signal -> guardrail -> order-builder offline.
    Strikes at 0.5% steps, OTM premiums shrink with distance (crude but sane).
    """
    out = []
    for i in range(-25, 26):
        strike = round(spot * (1 + 0.005 * i), 2)
        dist = abs(i)
        premium = round(spot * 0.004 * max(0.45, 1 - dist * 0.07), 2)
        for typ in ("call", "put"):
            out.append({
                "symbol": f"{underlying}260828C{int(strike * 1000):08d}" if typ == "call"
                else f"{underlying}260828P{int(strike * 1000):08d}",
                "type": typ,
                "strike": strike,
                "exp": "2026-08-28",
                "bid": round(premium * 0.95, 2),
                "ask": round(premium * 1.05, 2),
                "open_interest": 100,
            })
    return out


def option_chain(underlying: str) -> list[dict]:
    """Latest option chain for one underlying (public data)."""
    client = OptionHistoricalDataClient()
    try:
        chain = client.get_option_chain(OptionChainRequest(underlying_symbol=underlying))
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


def _guard_legs(legs: list[dict], intent: str) -> dict | None:
    """Shared pre-broker guardrails. Returns error dict, or None if OK."""
    if not (2 <= len(legs) <= 4):
        return {"error": "leg_count", "detail": "mleg requires 2..4 legs"}
    if len({l["symbol"] for l in legs}) != len(legs):
        return {"error": "dup_symbol", "detail": "all legs must have unique symbols"}
    if not isinstance(intent, str) or intent.lower() not in _POS_INTENT:
        return {"error": "bad_intent", "detail": "use bto|btc|sto|stc"}
    for leg in legs:
        notional = abs(leg["qty"]) * leg.get("premium", 0.0)
        if notional > MAX_OPTION_NOTIONAL:
            log.warning("leg %s notional %.2f exceeds cap %.2f; refusing order",
                        leg["symbol"], notional, MAX_OPTION_NOTIONAL)
            return {"error": "notional_cap", "leg": leg["symbol"]}
        if notional < MIN_ORDER_NOTIONAL:
            log.warning("leg %s notional %.2f below floor %.2f; refusing order",
                        leg["symbol"], notional, MIN_ORDER_NOTIONAL)
            return {"error": "min_notional", "leg": leg["symbol"]}
    return None


def submit_multi_leg(legs: list[dict], intent: str) -> dict:
    """Submit a multi-leg paper option order (wheel: CSP / credit spread).

    legs: [{symbol, qty, side, premium}] where side is 'buy'|'sell';
          qty is the leg ratio (maps to OptionLegRequest.ratio_qty).
    intent: 'bto'|'btc'|'sto'|'stc'.
    ENFORCES per-leg notional cap + floor before submit (same guard as demo).
    """
    err = _guard_legs(legs, intent)
    if err:
        return err
    req_legs = [
        OptionLegRequest(
            symbol=leg["symbol"],
            ratio_qty=leg["qty"],   # alpaca-py 0.43.5: ratio_qty (not qty) is the required leg field
            side=leg["side"],
        )
        for leg in legs
    ]
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


def demo_run(symbol: str = "SPY", lookback: int = 390) -> dict:
    """Key-free demo: yfinance bars + synthetic chain -> signal -> guarded proposal -> simulated fill.

    Lets us produce the 90-second demo video even before paper keys land.
    No broker is touched; the SAME _guard_legs checks run as in submit_multi_leg.
    Output is a dict of everything a video needs (signal, proposal, sim fill).
    """
    from datetime import datetime, timezone

    bars = demo_bars(symbol, lookback)
    if bars.empty:
        return {"error": "no_bars", "detail": f"{symbol} returned no bars"}
    close = bars["close"]
    last = float(close.iloc[-1])
    sma20 = float(close.rolling(20).mean().iloc[-1])
    sma60 = float(close.rolling(60).mean().iloc[-1])
    ret_1h = float(close.iloc[-1] / close.iloc[-61] - 1) if len(close) > 61 else 0.0
    # naive momentum state machine for the demo narrative
    if last > sma20 > sma60 and ret_1h > 0:
        bias = "bullish"
    elif last < sma20 < sma60 and ret_1h < 0:
        bias = "bearish"
    else:
        bias = "neutral"

    chain = demo_chain(symbol, last)
    puts = [c for c in chain if c["type"] == "put"]
    if bias == "bearish" and puts:
        # propose a cash-secured put (sell-to-open) below spot
        put = min(puts, key=lambda c: abs(c["strike"] - last * 0.97))
        legs = [{"symbol": put["symbol"], "qty": 1, "side": "sell", "premium": put["bid"] or put["ask"]}]
        intent = "sto"
        narrative = "bearish momentum -> sell a cash-secured put below spot, collect premium"
    else:
        # credit put spread (or neutral: covered-call-style sell-to-open call)
        calls = [c for c in chain if c["type"] == "call"]
        if bias == "bullish" and calls:
            call = min(calls, key=lambda c: abs(c["strike"] - last * 1.03))
            legs = [{"symbol": call["symbol"], "qty": 1, "side": "sell", "premium": call["bid"] or call["ask"]}]
            intent = "sto"
            narrative = "bullish signed -> sell a covered call at 3% OTM, harvest premium"
        else:
            # neutral: put credit spread (sell far-OTM put, buy closer-OTM put as hedge)
            if not puts:
                return {"ok": False, "error": "no_chain", "symbol": symbol}
            sell_put = min(puts, key=lambda c: abs(c["strike"] - last * 0.97))
            buy_put = min(puts, key=lambda c: abs(c["strike"] - last * 0.93))
            if sell_put["symbol"] == buy_put["symbol"]:
                return {"ok": False, "error": "thin_chain", "symbol": symbol}
            legs = [
                {"symbol": sell_put["symbol"], "qty": 1, "side": "sell", "premium": sell_put["bid"] or sell_put["ask"]},
                {"symbol": buy_put["symbol"], "qty": 1, "side": "buy", "premium": buy_put["ask"] or buy_put["bid"]},
            ]
            intent = "sto"
            narrative = "neutral -> put credit spread: sell 3% OTM put, buy 7% OTM put, defined risk"

    err = _guard_legs(legs, intent)
    if err:
        return {"ok": False, **err}
    premium = sum(abs(l["qty"]) * l.get("premium", 0.0) for l in legs)
    return {
        "ok": True,
        "sim": True,
        "symbol": symbol,
        "ts": datetime.now(timezone.utc).isoformat(),
        "bias": bias,
        "last": last,
        "sma20": sma20,
        "sma60": sma60,
        "narrative": narrative,
        "intent": intent,
        "legs": legs,
        "notional": premium,
        "data": {"bars": "yfinance 5m (key-free)", "chain": "synthetic around spot (Alpaca chain needs keys)"},
        "fills": [{"symbol": l["symbol"], "side": l["side"], "qty": l["qty"], "premium": l.get("premium", 0.0)} for l in legs],
        "note": "SIMULATED FILL - no order submitted to Alpaca (no keys / paper-only demo)",
    }


def main() -> None:
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Options/equities agent (paper).")
    ap.add_argument("--demo", action="store_true", help="key-free simulated demo run (no broker)")
    ap.add_argument("--symbol", default="SPY", help="underlying for demo")
    ap.add_argument("--lookback", type=int, default=390, help="bars to fetch (default 390 = ~1 session)")
    args = ap.parse_args()

    if args.demo:
        out = demo_run(args.symbol, args.lookback)
        print(json.dumps(out, indent=2, default=str))
        if not out.get("ok"):
            raise SystemExit(1)
        raise SystemExit(0)
    raise SystemExit("No mode given; use --demo (paper-live mode needs ALPACA keys).")


if __name__ == "__main__":
    main()
