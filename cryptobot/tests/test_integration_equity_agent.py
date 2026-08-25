"""Contract-level integration tests for equity_agent's LIVE (keyed) code paths.

These exercise the exact client-return shapes equity_agent will see against the
real Alpaca paper API, WITHOUT needing ALPACA_API_KEY/ALPACA_SECRET_KEY. They use
fake clients whose attributes mirror alpaca-py 0.43.5 responses, so any shape
mismatch in response parsing / bar indexing / chain mapping fails HERE instead
of on the first live paper order after keys land.

The existing test suite covers guardrails + demo path; this file covers the
three paths that were only smoke-covered: submit_multi_leg, equity_bars,
option_chain.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot import equity_agent as ea  # noqa: E402
from bot.equity_agent import (  # noqa: E402
    equity_bars,
    option_chain,
    submit_multi_leg,
)

FAKE_ORDER_ID = "f17f0c34-6f5d-4f8d-8b56-abcdef012345"


# ---------- fake alpaca-py return shapes ----------

class _FakeOrder:
    """Mirrors alpaca.trading.models.Order (resp from client.submit_order)."""

    def __init__(self, id=FAKE_ORDER_ID, status="accepted"):
        self.id = id
        self.status = status


class _FakeTradingClient:
    def __init__(self, *args, **kwargs):
        self.submitted = []

    def submit_order(self, order):
        self.submitted.append(order)
        return _FakeOrder()


class _FakeStockClient:
    """Mirrors StockHistoricalDataClient: get_stock_bars(req).df multi-symbol MultiIndex."""

    def __init__(self, *args, **kwargs):
        idx = pd.MultiIndex.from_product(
            [["SPY"], pd.date_range("2026-08-24 09:31", periods=70, freq="min")],
            names=["symbol", "timestamp"],
        )
        self.df = pd.DataFrame(
            {
                "open": [100.0] * 70,
                "high": [101.0] * 70,
                "low": [99.0] * 70,
                "close": [100.5] * 70,
                "volume": [1000] * 70,
                "trade_count": [10] * 70,
                "vwap": [100.4] * 70,
            },
            index=idx,
        )

    def get_stock_bars(self, req):
        return self


class _FakeChainItem:
    """Mirrors an OptionChainData item (symbol/type/strike_price/...)."""

    def __init__(self, symbol, typ, strike, exp, bid, ask, oi):
        self.symbol = symbol
        self.type = typ
        self.strike_price = strike
        self.expiration_date = exp
        self.bid = bid
        self.ask = ask
        self.open_interest = oi


class _FakeOptionDataClient:
    def __init__(self, *args, **kw):
        self._items = [
            _FakeChainItem("SPY260828C00490000", "call", 490.0, "2026-08-28", 2.10, 2.15, 5000),
            _FakeChainItem("SPY260828P00460000", "put", 460.0, "2026-08-28", 2.00, 2.05, 3000),
        ]

    def get_option_chain(self, req):
        return self._items


# --- submit_multi_leg: response parsing + order construction ---

def test_submit_multi_leg_returns_id_and_status(monkeypatch):
    """Live path: 2-leg spread submits, resp.id/status parsed, no AttributeError."""
    client = _FakeTradingClient()
    monkeypatch.setattr(ea, "TradingClient", lambda *a, **k: client)
    res = submit_multi_leg(
        [
            {"symbol": "SPY260828C00490000", "qty": 1, "side": "sell", "premium": 2.10},
            {"symbol": "SPY260828P00460000", "qty": 1, "side": "buy", "premium": 2.00},
        ],
        "bto",
    )
    assert res["order_id"] == FAKE_ORDER_ID
    assert res["status"] == "accepted"
    assert res["legs"] == 2


def test_submit_multi_leg_builds_mleg_request(monkeypatch):
    client = _FakeTradingClient()
    monkeypatch.setattr(ea, "TradingClient", lambda *a, **k: client)
    submit_multi_leg(
        [
            {"symbol": "SPY260828C00490000", "qty": 1, "side": "sell", "premium": 2.10},
            {"symbol": "SPY260828P00460000", "qty": 2, "side": "buy", "premium": 2.00},
        ],
        "bto",
    )
    assert len(client.submitted) == 1
    req = client.submitted[0]
    assert req.order_class.name == "MLEG"
    assert req.type.name == "MARKET"
    assert req.position_intent.name == "BUY_TO_OPEN"
    assert req.time_in_force.name == "DAY"
    assert len(req.legs) == 2
    assert req.legs[0].ratio_qty == 1 and req.legs[1].ratio_qty == 2
    assert req.legs[0].symbol == "SPY260828C00490000"


def test_submit_multi_leg_surfaces_api_errors(monkeypatch):
    class _BoomClient:
        def submit_order(self, order):
            raise RuntimeError("insufficient buying power")

    monkeypatch.setattr(ea, "TradingClient", lambda *a, **k: _BoomClient())
    res = submit_multi_leg(
        [
            {"symbol": "SPY261099C00490000", "qty": 1, "side": "sell", "premium": 2.10},
            {"symbol": "SPY261099P00460000", "qty": 1, "side": "buy", "premium": 2.00},
        ],
        "sto",
    )
    assert res["error"] == "submit"
    assert "insufficient buying power" in res["detail"]


# --- equity_bars: multi-level MultiIndex unwrap + column slice ---

def test_equity_bars_flattens_and_selects_columns(monkeypatch):
    monkeypatch.setattr(ea, "StockHistoricalDataClient", lambda *a, **k: _FakeStockClient())
    df = equity_bars("SPY", lookback=60)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 60
    assert isinstance(df.index, pd.DatetimeIndex)


# --- option_chain: chain item field mapping ---

def test_option_chain_maps_fields(monkeypatch):
    monkeypatch.setattr(ea, "OptionHistoricalDataClient", lambda *a, **k: _FakeOptionDataClient())
    chain = option_chain("SPY")
    assert len(chain) == 2
    assert chain[0] == {
        "symbol": "SPY260828C00490000",
        "type": "call",
        "strike": 490.0,
        "exp": "2026-08-28",
        "bid": 2.1,
        "ask": 2.15,
        "open_interest": 5000,
    }
