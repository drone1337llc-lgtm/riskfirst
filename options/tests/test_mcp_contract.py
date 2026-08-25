"""Contract tests for the REAL Alpaca MCP live lane (options/options/client.py).

These exercise the exact response shapes the Alpaca MCP server returns
(get_option_chain items, get_account_info text, place_option_order args)
WITHOUT network or keys: McpClient._request is monkeypatched to canned
shapes, and the subprocess env is inspected to prove paper-forcing.

Any schema drift between the MCP server and our parsing fails HERE, not on
the first live paper order after keys land.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from options import client as cl  # noqa: E402
from options.strategies import OrderProposal  # noqa: E402


# --------------------------------------------------------------------------- #
# Realistic MCP get_option_chain item shapes
# --------------------------------------------------------------------------- #
def _chain_item(**over):
    item = {
        "symbol": "SPY260918C00560000",
        "underlying_symbol": "SPY",
        "strike_price": 560.0,
        "expiration_date": "2026-09-18",
        "type": "call",
        "open_interest": 1250,
        "underlying_price": 561.2,
        "quote": {"bid_price": 2.35, "ask_price": 2.41},
        "greeks": {
            "delta": 0.52, "gamma": 0.012, "theta": -0.31,
            "vega": 0.24, "rho": 0.05, "iv": 0.27,
        },
    }
    item.update(over)
    return item


class FakeRequests:
    """Stand-in for McpClient._request; records calls, returns canned data."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, params):
        self.calls.append((method, params))
        return self.responses.pop(0) if self.responses else {}


def make_client(fake):
    """McpClient with _request monkeypatched; no subprocess is spawned."""
    c = cl.McpClient.__new__(cl.McpClient)
    c._request = fake
    c._server = {"name": "Alpaca MCP Server", "version": "3.4.7"}
    return c


def proposal(side="sell_to_open", symbol="SPY260918C00560000"):
    return OrderProposal(
        strategy="covered_call", symbol=symbol, underlying="SPY",
        side=side, qty=2, price=2.38, delta=-0.24, dte=24,
        iv_rank=0.7, notional=112000,
    )


# --------------------------------------------------------------------------- #
# Order mapping -> place_option_order args
# --------------------------------------------------------------------------- #
class TestOrderMapping:
    def test_sell_to_open_maps_side_and_intent(self):
        args = cl.build_order_args(proposal("sell_to_open"))
        assert args["side"] == "sell"
        assert args["position_intent"] == "sell_to_open"
        assert args["qty"] == "2"
        assert args["type"] == "market"
        assert args["time_in_force"] == "day"
        assert args["symbol"] == "SPY260918C00560000"

    def test_buy_to_open_maps_side_and_intent(self):
        args = cl.build_order_args(proposal("buy_to_open", "SPY260918P00560000"))
        assert args["side"] == "buy"
        assert args["position_intent"] == "buy_to_open"


# --------------------------------------------------------------------------- #
# Chain parsing
# --------------------------------------------------------------------------- #
class TestChainParsing:
    def test_parses_chain_item(self):
        o = cl.parse_option(_chain_item(), "SPY")
        assert o is not None
        assert o.symbol == "SPY260918C00560000"
        assert o.underlying == "SPY"
        assert o.is_call is True
        assert o.strike == 560.0
        assert o.dte > 0
        assert o.open_interest == 1250
        assert o.bid == pytest.approx(2.35)
        assert o.ask == pytest.approx(2.41)
        assert o.mid == pytest.approx(2.38)
        assert o.g is not None and o.g.delta == pytest.approx(0.52)
        assert o.iv == pytest.approx(0.27)

    def test_parses_put_with_flat_keys(self):
        item = {
            "symbol": "QQQ260918P00480000",
            "strike_price": 480.0,
            "expiration_date": "2026-09-18",
            "type": "put",
            "open_interest": 900,
            "underlying_price": 481.0,
            "bid_price": 3.1,
            "ask_price": 3.2,
            "greeks": {"delta": -0.48, "iv": 0.24},
        }
        o = cl.parse_option(item, "QQQ")
        assert o is not None
        assert o.is_call is False
        assert o.delta == pytest.approx(-0.48)
        assert o.bid == pytest.approx(3.1)

    def test_malformed_item_skipped(self):
        assert cl.parse_option({"symbol": "X"}, "SPY") is None

    def test_get_contracts_single_chain_call(self):
        fake = FakeRequests([{"chain": [_chain_item()]}])
        c = make_client(fake)
        chain = c.get_contracts("SPY")
        assert [m for m, _ in fake.calls] == ["tools/call"]
        args0 = fake.calls[0][1]["arguments"]
        assert fake.calls[0][1]["name"] == "get_option_chain"
        assert args0["underlying_symbol"] == "SPY"
        assert args0["limit"] == 250
        assert len(chain) == 1
        assert chain[0].symbol == "SPY260918C00560000"

    def test_get_contracts_filters_outside_dte_window(self):
        old = _chain_item(expiration_date="2026-12-18")  # ~115 DTE, out of window
        inwin = _chain_item()                            # ~24 DTE
        fake = FakeRequests([{"chain": [old, inwin]}])
        c = make_client(fake)
        chain = c.get_contracts("SPY")
        assert len(chain) == 1
        assert chain[0].expiry.isoformat() == "2026-09-18"


# --------------------------------------------------------------------------- #
# Account / positions / order / flatten
# --------------------------------------------------------------------------- #
class TestAccount:
    def test_get_account_parses_formatted_text(self):
        text = (
            "Account\n"
            "Equity: $100,000.00\n"
            "Cash: $60,000.00\n"
            "Buying Power: $100,000.00\n"
        )
        fake = FakeRequests([{"text": text}])
        c = make_client(fake)
        acct = c.get_account()
        assert fake.calls[0][1]["name"] == "get_account_info"
        assert acct["equity"] == pytest.approx(100_000.0)
        assert acct["cash"] == pytest.approx(60_000.0)
        assert acct["buying_power"] == pytest.approx(100_000.0)

    def test_get_account_parses_content_wrapped_text(self):
        text = (
            "Account\n"
            "Equity: $100,000.00\n"
            "Cash: $60,000.00\n"
            "Buying Power: $100,000.00\n"
        )
        wrapped = {"content": [{"type": "text", "text": text}]}
        fake = FakeRequests([wrapped])
        c = make_client(fake)
        acct = c.get_account()
        assert acct["equity"] == pytest.approx(100_000.0)

    def test_get_account_parses_json_object_text(self):
        payload = {"equity": 100000.0, "cash": 60000.0, "buying_power": 100000.0}
        fake = FakeRequests([{"content": [{"type": "text", "text": json.dumps(payload)}]}])
        c = make_client(fake)
        acct = c.get_account()
        assert acct["equity"] == pytest.approx(100_000.0)
        assert acct["cash"] == pytest.approx(60_000.0)
        assert acct["buying_power"] == pytest.approx(100_000.0)


class TestPositions:
    def test_get_positions_parses_list(self):
        fake = FakeRequests([{
            "positions": [
                {"symbol": "SPY", "qty": 200, "asset_class": "us_equity"},
                {"symbol": "SPY260918C00560000", "qty": 1, "asset_class": "us_option"},
            ]
        }])
        c = make_client(fake)
        pos = c.get_positions()
        assert len(pos) == 2
        assert pos[0]["symbol"] == "SPY"
        assert pos[1]["asset_class"] == "us_option"

    def test_get_positions_parses_content_wrapped_json(self):
        payload = [
            {"symbol": "SPY", "qty": 200, "asset_class": "us_equity"},
        ]
        wrapped = {"content": [{"type": "text", "text": json.dumps(payload)}]}
        fake = FakeRequests([wrapped])
        c = make_client(fake)
        pos = c.get_positions()
        assert len(pos) == 1
        assert pos[0]["symbol"] == "SPY"
        assert pos[0]["qty"] == 200


class TestOrderSubmission:
    def test_submit_order_calls_place_option_order(self):
        fake = FakeRequests([{"order_id": "abc123", "status": "accepted"}])
        c = make_client(fake)
        res = c.submit_order(proposal())
        assert fake.calls[0][1]["name"] == "place_option_order"
        assert res["status"] == "submitted"


class TestFlatten:
    def test_flatten_calls_close_all(self):
        fake = FakeRequests([{}])
        c = make_client(fake)
        c.flatten()
        assert fake.calls[0][1]["name"] == "close_all_positions"


# --------------------------------------------------------------------------- #
# Paper-forcing rail: the subprocess env must pin ALPACA_PAPER=true
# --------------------------------------------------------------------------- #
class TestPaperRail:
    def test_mcp_env_forces_paper(self):
        captured = {}

        class _Pipe:
            def write(self, s):
                return len(s)

            def flush(self):
                pass

            def readline(self):
                return json.dumps({
                    "jsonrpc": "2.0", "id": 1,
                    "result": {"serverInfo": {"name": "Alpaca MCP Server"}},
                }) + "\n"

        class FakePopen:
            def __init__(self, cmd, **kwargs):
                captured["cmd"] = cmd
                captured["env"] = kwargs["env"]
                self.stdin = _Pipe()
                self.stdout = _Pipe()

            def wait(self, timeout=None):
                return 0

            def terminate(self):
                pass

        monkeypatch_env = {
            "ALPACA_API_KEY": "PKTESTKEY123",
            "ALPACA_SECRET_KEY": "testsecret",
            "PATH": "/usr/bin:/bin",
        }
        orig_popen = cl.subprocess.Popen
        cl.subprocess.Popen = FakePopen
        try:
            import os
            saved = {k: os.environ.get(k) for k in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")}
            os.environ["ALPACA_API_KEY"] = "PKTESTKEY123"
            os.environ["ALPACA_SECRET_KEY"] = "testsecret"
            try:
                c = cl.McpClient()
                c.close()
            finally:
                for k, v in saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
        finally:
            cl.subprocess.Popen = orig_popen

        env = captured["env"]
        assert env["ALPACA_PAPER"] == "true"
        assert env["ALPACA_API_KEY"] == "PKTESTKEY123"
        assert env["ALPACA_SECRET_KEY"] == "testsecret"
        assert "ALPACA_OPTIONS_LEVEL" in env
