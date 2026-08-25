"""Offline tests for the LLM risk referee.

No network, no keys, no live Ollama — the referee is exercised with a fake
transport injected via monkeypatch so verdict parsing and fail-open behavior
are deterministic.
"""
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from options import options as opt, strategies as strat
from options.agent import RiskArbiter, Agent
from options.client import MockClient
from options.llm_referee import LLMReferee, _parse_verdict
import options.llm_referee as mod

TODAY = date(2026, 8, 24)


def make_contract(strike, is_call, spot=560.0, oi=500, dte=21, iv_rank=0.7,
                  expiry=None, iv=0.25):
    expiry = expiry or (TODAY + timedelta(days=dte))
    o = opt.Option(
        symbol=f"SPY{expiry:%y%m%d}{'C' if is_call else 'P'}{int(strike*1000):08d}",
        underlying="SPY", strike=strike, expiry=expiry, is_call=is_call,
        bid=2.0, ask=2.10, mid=2.05, open_interest=oi, spot=spot,
        dte=dte, iv=iv, iv_rank=iv_rank, score=2.05,
    )
    o.g = opt.greeks(spot, strike, dte / 365.0, 0.05, iv, is_call)
    return o


def make_proposal(strategy="cash_secured_put", qty=1, price=2.05, notional=52_000):
    return strat.OrderProposal(
        strategy=strategy, symbol="SPY260918P05200000", underlying="SPY",
        side="sell_to_open", qty=qty, price=price, delta=0.25, dte=21,
        iv_rank=0.7, notional=notional, reason="test",
    )


class TestVerdictParsing(unittest.TestCase):
    def test_strict_json_approve(self):
        self.assertEqual(_parse_verdict('{"approve": true, "reason": "ok"}'),
                         (True, "ok"))

    def test_strict_json_veto(self):
        self.assertEqual(_parse_verdict('{"approve": false, "reason": "no shares"}'),
                         (False, "no shares"))

    def test_json_embedded_in_prose(self):
        text = ("Sure! Here is my review.\n"
                '{"approve": false, "reason": "hedge adds risk"}\nHope that helps.')
        self.assertEqual(_parse_verdict(text), (False, "hedge adds risk"))

    def test_garbage_returns_none(self):
        self.assertIsNone(_parse_verdict("I think this trade is fine, approved!"))
        self.assertIsNone(_parse_verdict(""))
        self.assertIsNone(_parse_verdict("no braces here"))

    def test_non_bool_approve_returns_none(self):
        self.assertIsNone(_parse_verdict('{"approve": "yes", "reason": "x"}'))

    def test_missing_reason_fills_default(self):
        self.assertEqual(_parse_verdict('{"approve": false}'), (False, "no reason given"))


class TestRefereeBehavior(unittest.TestCase):
    def test_unreachable_fails_open(self):
        r = LLMReferee(url="http://127.0.0.1:1", timeout=0.3)
        approve, reason = r.review(make_proposal(), {"equity": 100_000}, 80_000)
        self.assertTrue(approve)          # fail-open: never blocks on outage
        self.assertIn("unreachable", reason)

    def test_veto_opinion_does_not_block_in_advisory_mode(self):
        r = LLMReferee()                  # enforce defaults to False
        original = mod._ask_ollama
        mod._ask_ollama = lambda *a, **k: '{"approve": false, "reason": "IV too low"}'
        try:
            approve, reason = r.review(make_proposal(), {"equity": 100_000}, 80_000)
            self.assertFalse(approve)     # opinion recorded...
            self.assertFalse(r.enforce)   # ...but advisory-only
        finally:
            mod._ask_ollama = original

    def test_approve_passes(self):
        r = LLMReferee()
        original = mod._ask_ollama
        mod._ask_ollama = lambda *a, **k: '{"approve": true, "reason": "clean"}'
        try:
            approve, reason = r.review(make_proposal(), {"equity": 100_000}, 80_000)
            self.assertTrue(approve)
        finally:
            mod._ask_ollama = original

    def test_garbage_response_fails_open(self):
        r = LLMReferee()
        original = mod._ask_ollama
        mod._ask_ollama = lambda *a, **k: "The trade looks fine to me."
        try:
            approve, reason = r.review(make_proposal(), {"equity": 100_000}, 80_000)
            self.assertTrue(approve)
            self.assertIn("no structured opinion", reason)
        finally:
            mod._ask_ollama = original

    def test_enforce_mode_vetoes(self):
        r = LLMReferee(enforce=True)
        original = mod._ask_ollama
        mod._ask_ollama = lambda *a, **k: '{"approve": false, "reason": "bad structure"}'
        try:
            approve, reason = r.review(make_proposal(), {"equity": 100_000}, 80_000)
            self.assertFalse(approve)
        finally:
            mod._ask_ollama = original


class TestArbiterIntegration(unittest.TestCase):
    def test_advisory_opinion_does_not_block_trade(self):
        """LLM 'approve:false' in advisory mode => trade still executes."""
        client = MockClient(equity=100_000, today=TODAY)
        client.set_shares("SPY", 300)
        client.set_cash(80_000)
        referee = LLMReferee()            # advisory
        original = mod._ask_ollama
        mod._ask_ollama = lambda *a, **k: '{"approve": false, "reason": "low IV"}'
        agent = Agent(client=client, db_path=":memory:", referee=referee)
        try:
            decisions = agent.run_cycle()
            self.assertGreater(len(decisions), 0)   # trades went through
        finally:
            mod._ask_ollama = original
            agent.close()

    def test_enforce_veto_blocks_trade(self):
        client = MockClient(equity=100_000, today=TODAY)
        client.set_shares("SPY", 300)
        client.set_cash(80_000)
        referee = LLMReferee(enforce=True)
        original = mod._ask_ollama
        mod._ask_ollama = lambda *a, **k: '{"approve": false, "reason": "no confidence"}'
        agent = Agent(client=client, db_path=":memory:", referee=referee)
        try:
            decisions = agent.run_cycle()
            self.assertEqual(decisions, [])  # nothing executed
        finally:
            mod._ask_ollama = original
            agent.close()

    def test_agent_cycle_runs_with_referee_approving(self):
        client = MockClient(equity=100_000, today=TODAY)
        client.set_shares("SPY", 300)
        client.set_cash(80_000)
        referee = LLMReferee()
        original = mod._ask_ollama
        mod._ask_ollama = lambda *a, **k: '{"approve": true, "reason": "clean"}'
        agent = Agent(client=client, db_path=":memory:", referee=referee)
        try:
            decisions = agent.run_cycle()
            self.assertIsInstance(decisions, list)
        finally:
            mod._ask_ollama = original
            agent.close()


if __name__ == "__main__":
    unittest.main()
