"""Alpaca paper execution + guardrails. The ONLY module that touches the broker."""
import logging

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

import config

log = logging.getLogger("execute")

assert config.ALPACA_PAPER, "Refusing to construct executor without paper mode."

_client = TradingClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, paper=True)
_ALPACA_SYMBOL = config.SYMBOL  # e.g. "ETH/USD"


def account_state() -> dict:
    acct = _client.get_account()
    cash = float(acct.cash)
    asset_qty, asset_val = 0.0, 0.0
    for pos in _client.get_all_positions():
        if pos.symbol.replace("USD", "/USD") == _ALPACA_SYMBOL or pos.symbol == _ALPACA_SYMBOL.replace("/", ""):
            asset_qty = float(pos.qty)
            asset_val = float(pos.market_value)
    nw = cash + asset_val
    return {"cash": cash, "asset_qty": asset_qty, "asset_value": asset_val,
            "net_worth": nw, "allocation": asset_val / nw if nw > 0 else 0.0}


def rebalance_to(target_alloc: float, macro_cap: float) -> dict:
    """Move toward target allocation, hard-capped by the LLM's macro cap.

    Order size = min(agent's request, cap) — the guardrail from the design doc.
    """
    target = min(max(0.0, target_alloc), max(0.0, min(1.0, macro_cap)))
    st = account_state()
    delta_usd = target * st["net_worth"] - st["asset_value"]

    if abs(delta_usd) < max(config.MIN_ORDER_NOTIONAL, 0.005 * st["net_worth"]):
        log.info("no-op: alloc %.2f -> %.2f (delta $%.2f below min)",
                 st["allocation"], target, delta_usd)
        return {"action": "hold", **st}

    side = OrderSide.BUY if delta_usd > 0 else OrderSide.SELL
    notional = round(min(abs(delta_usd), st["cash"] if side == OrderSide.BUY
                         else st["asset_value"]), 2)
    if notional < config.MIN_ORDER_NOTIONAL:
        return {"action": "hold", **st}

    order = _client.submit_order(MarketOrderRequest(
        symbol=_ALPACA_SYMBOL, notional=notional, side=side,
        time_in_force=TimeInForce.GTC))
    log.info("submitted %s $%.2f (alloc %.2f -> %.2f, cap %.2f) id=%s",
             side.value, notional, st["allocation"], target, macro_cap, order.id)
    return {"action": side.value, "notional": notional, "order_id": str(order.id), **st}
