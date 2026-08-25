"""Guardrail tests for bot.equity_agent — options/equities lane (Alpaca paper).

Covers the risk rails that must hold BEFORE any broker contact:
  - mleg leg-count bound (2..4)
  - unique leg symbols
  - intent whitelist (bto|btc|sto|stc)
  - per-leg notional cap ($500)
  - paper-only TradingClient construction (paper=True), MLEG class, DAY TIF
  - submit failure surfaces as {"error": "submit"}
  - option_chain degrades to [] on broker error

Run from cryptobot/ dir:  python -m pytest tests/ -v
No network, no keys: TradingClient is mocked at construction.
"""
from __future__ import annotations

import pytest

from alpaca.trading.enums import OrderClass, PositionIntent, TimeInForce
from alpaca.trading.requests import OptionLegRequest

import config
from bot import equity_agent as ea


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class FakeSubmitter:
    """Replaces alpaca TradingClient; records constructor + order, returns canned resp."""

    def __init__(self, *a, **kw):
        self.constructed = {"args": a, "kwargs": kw}

    def submit_order(self, order):
        self.order = order
        return FakeResp()


class FakeResp:
    id = "fake-order-123"
    status = "accepted"


def make_leg(symbol="SPY", qty=1, side="sell", premium=100.0):
    return {"symbol": symbol, "qty": qty, "side": side, "premium": premium}


@pytest.fixture
def fake_client(monkeypatch):
    fake = FakeSubmitter()

    def _make(*a, **kw):
        fake.constructed = {"args": a, "kwargs": kw}
        return fake

    monkeypatch.setattr(ea, "TradingClient", _make)
    return fake


# ---------------------------------------------------------------------------
# leg-count guardrail
# ---------------------------------------------------------------------------

def test_leg_count_too_few():
    r = ea.submit_multi_leg([make_leg()], "sto")
    assert r["error"] == "leg_count"


def test_leg_count_too_many():
    legs = [make_leg(symbol=s) for s in ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]]
    r = ea.submit_multi_leg(legs, "sto")
    assert r["error"] == "leg_count"


def test_leg_count_2_and_4_accepted(fake_client):
    two = ea.submit_multi_leg([make_leg("SPY"), make_leg("QQQ")], "bto")
    assert "error" not in two
    four = ea.submit_multi_leg(
        [make_leg(s) for s in ["SPY", "QQQ", "AAPL", "MSFT"]], "bto")
    assert "error" not in four


# ---------------------------------------------------------------------------
# duplicate-symbol guardrail
# ---------------------------------------------------------------------------

def test_dup_symbol_rejected():
    legs = [make_leg("SPY", side="sell"), make_leg("SPY", side="buy")]
    r = ea.submit_multi_leg(legs, "sto")
    assert r["error"] == "dup_symbol"


# ---------------------------------------------------------------------------
# intent whitelist
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("intent", ["bto", "btc", "sto", "stc"])
def test_valid_intents_accepted(fake_client, intent):
    legs = [make_leg("SPY"), make_leg("QQQ")]
    r = ea.submit_multi_leg(legs, intent)
    assert "error" not in r


@pytest.mark.parametrize("intent", ["", "hodl", "buy", None])
def test_bad_intent_rejected(intent):
    legs = [make_leg("SPY"), make_leg("QQQ")]
    r = ea.submit_multi_leg(legs, intent)
    assert r["error"] == "bad_intent"


def test_uppercase_intent_accepted(fake_client):
    # guard lowercases by design; "BTO" is accepted and mapped to BUY_TO_OPEN
    legs = [make_leg("SPY"), make_leg("QQQ")]
    r = ea.submit_multi_leg(legs, "BTO")
    assert "error" not in r
    assert fake_client.order.position_intent == PositionIntent.BUY_TO_OPEN


# ---------------------------------------------------------------------------
# notional cap
# ---------------------------------------------------------------------------

def test_notional_cap_rejects_over():
    legs = [make_leg("SPY", qty=6, premium=100.0), make_leg("QQQ", qty=1, premium=100.0)]
    r = ea.submit_multi_leg(legs, "sto")
    assert r["error"] == "notional_cap"
    assert r["leg"] == "SPY"


def test_notional_at_cap_accepted(fake_client):
    # exactly $500 (qty 5 x premium 100) -> allowed; boundary is strictly >
    legs = [make_leg("SPY", qty=5, premium=100.0), make_leg("QQQ", qty=1, premium=100.0)]
    r = ea.submit_multi_leg(legs, "sto")
    assert "error" not in r


# ---------------------------------------------------------------------------
# order plumbing (what actually hits the broker when guards pass)
# ---------------------------------------------------------------------------

def test_submit_plumbing_paper_mleg_day(fake_client):
    legs = [make_leg("SPY", qty=1, side="sell", premium=100.0),
            make_leg("QQQ", qty=1, side="buy", premium=95.0)]
    r = ea.submit_multi_leg(legs, "sto")
    assert r["order_id"] == "fake-order-123"
    assert r["status"] == "accepted"
    assert r["legs"] == 2

    # paper-only client
    assert fake_client.constructed["kwargs"]["paper"] is True
    order = fake_client.order
    assert order.order_class == OrderClass.MLEG
    assert order.position_intent == PositionIntent.SELL_TO_OPEN
    assert order.time_in_force == TimeInForce.DAY
    # leg plumbing: OptionLegRequest each, side preserved, first symbol as anchor
    assert len(order.legs) == 2
    assert all(isinstance(l, OptionLegRequest) for l in order.legs)
    assert order.legs[0].symbol == "SPY" and order.legs[0].side == "sell"
    assert order.legs[1].symbol == "QQQ" and order.legs[1].side == "buy"
    assert order.symbol == "SPY"


@pytest.mark.parametrize("intent,expected", [
    ("bto", PositionIntent.BUY_TO_OPEN),
    ("btc", PositionIntent.BUY_TO_CLOSE),
    ("sto", PositionIntent.SELL_TO_OPEN),
    ("stc", PositionIntent.SELL_TO_CLOSE),
])
def test_intent_mapping_to_position_intent(fake_client, intent, expected):
    legs = [make_leg("SPY"), make_leg("QQQ")]
    ea.submit_multi_leg(legs, intent)
    assert fake_client.order.position_intent == expected


def test_broker_error_surfaces(fake_client):
    def boom(order):
        raise RuntimeError("connect refused")
    fake_client.submit_order = boom
    legs = [make_leg("SPY"), make_leg("QQQ")]
    r = ea.submit_multi_leg(legs, "sto")
    assert r["error"] == "submit"
    assert "connect refused" in r["detail"]


# ---------------------------------------------------------------------------
# option_chain degrades gracefully without keys / on broker error
# ---------------------------------------------------------------------------

def test_option_chain_empty_on_error(monkeypatch):
    class BoomClient:
        def get_option_chain(self, req):
            raise RuntimeError("401 unauthorized")
    monkeypatch.setattr(ea, "OptionHistoricalDataClient", BoomClient)
    assert ea.option_chain("SPY") == []
