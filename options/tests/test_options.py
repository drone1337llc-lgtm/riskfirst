"""Offline unit tests for the Alpaca options agent.

All tests run with zero network and zero API keys using MockClient. Run:

    cd options
    python -m unittest discover -s tests -v
    # or
    python -m pytest tests -v
"""
import os
import sys
import unittest
import math
from datetime import date, timedelta

# Make the `options` package importable from the project root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from options import config, options as opt, strategies as strat
from options.client import MockClient
from options.agent import RiskArbiter, Agent

TODAY = date(2026, 8, 24)


def make_contract(strike, is_call, spot=560.0, oi=500, dte=21, iv_rank=0.7,
                  expiry=None, iv=0.25):
    """Build a contract with Greeks attached. bid/ask set by caller for tests."""
    expiry = expiry or (TODAY + timedelta(days=dte))
    o = opt.Option(
        symbol=f"SPY{expiry:%y%m%d}{'C' if is_call else 'P'}{int(strike*1000):08d}",
        underlying="SPY", strike=strike, expiry=expiry, is_call=is_call,
        bid=2.0, ask=2.10, mid=2.05, open_interest=oi, spot=spot,
        dte=dte, iv=iv, iv_rank=iv_rank, score=2.05,
    )
    o.g = opt.greeks(spot, strike, dte / 365.0, 0.05, iv, is_call)
    return o


class TestGreeks(unittest.TestCase):
    """Black-Scholes Greeks vs known reference values (offline)."""

    def test_call_price_at_the_money(self):
        # S=K=100, T=1y, r=5%, sigma=20% -> BS ATM call ~ 10.45
        price = opt.black_scholes(100, 100, 1.0, 0.05, 0.20, True)
        self.assertAlmostEqual(price, 10.45, delta=0.02)

    def test_put_call_parity_price(self):
        S, K, T, r, sig = 100, 100, 0.5, 0.05, 0.25
        call = opt.black_scholes(S, K, T, r, sig, True)
        put = opt.black_scholes(S, K, T, r, sig, False)
        lhs = call - put
        rhs = S - K * math.exp(-r * T)
        self.assertAlmostEqual(lhs, rhs, delta=0.001)

    def test_put_call_parity_delta(self):
        S, K, T, r, sig = 100, 100, 0.5, 0.05, 0.25
        gc = opt.greeks(S, K, T, r, sig, True)
        gp = opt.greeks(S, K, T, r, sig, False)
        self.assertAlmostEqual(gc.delta - gp.delta, 1.0, delta=1e-6)

    def test_deep_itm_call_delta_near_one(self):
        g = opt.greeks(100, 90, 0.1, 0.05, 0.20, True)
        self.assertGreater(g.delta, 0.8)

    def test_put_delta_negative(self):
        # A long put has negative delta; short side (sell) flips sign.
        g = opt.greeks(100, 110, 0.3, 0.05, 0.25, False)
        self.assertLess(g.delta, 0.0)
        self.assertGreater(g.delta, -1.0)

    def test_iv_recovered_from_price(self):
        iv_true = 0.32
        price = opt.black_scholes(100, 105, 0.5, 0.05, iv_true, True)
        iv_est = opt.implied_vol(100, 105, 0.5, 0.05, price, True)
        self.assertIsNotNone(iv_est)
        self.assertAlmostEqual(iv_est, iv_true, delta=0.01)


class TestSizing(unittest.TestCase):
    def test_never_exceeds_2pct(self):
        eq = 100_000.0
        qty = strat.size_contracts(eq, eq * 0.02, 0.05)
        self.assertLessEqual(qty * 0.05, eq * 0.02 + 1e-9)

    def test_size_respects_dollar_cap(self):
        eq = 100_000.0
        qty = strat.size_contracts(eq, 500.0, 50.0)  # 500/50 = 10
        self.assertEqual(qty, 10)

    def test_zero_price_returns_zero(self):
        self.assertEqual(strat.size_contracts(100_000, 2000, 0.0), 0)


class TestRiskArbiter(unittest.TestCase):
    def setUp(self):
        self.limits = config.RiskLimits()

    def _prop(self, notional=100.0, strategy="x"):
        return strat.OrderProposal(strategy, "S", "U", "buy_to_open", 1, 1.0,
                                   0.1, 21, 0.5, notional)

    def test_drawdown_pause_blocks(self):
        arb = RiskArbiter(self.limits)
        arb.update_high(100_000.0)
        acct = {"equity": 90_000}   # -10% -> exceeds -8%
        accepted, reason = arb.check(self._prop(), acct, cash=1_000_000)
        self.assertFalse(accepted)
        self.assertIn("drawdown", reason)

    def test_circuit_breaker_trips_at_10pct(self):
        arb = RiskArbiter(self.limits)
        arb.update_high(100_000.0)
        self.assertFalse(arb.circuit_breaker_tripped(91_000))   # -9%: not yet
        self.assertTrue(arb.circuit_breaker_tripped(89_900))     # -10.1%: trip

    def test_circuit_breaker_is_trailing(self):
        arb = RiskArbiter(self.limits)
        arb.update_high(100_000.0)
        self.assertTrue(arb.circuit_breaker_tripped(89_900))     # trip at -10.1%
        # New high-water mark resets the reference: no longer tripped.
        self.assertFalse(arb.circuit_breaker_tripped(105_000))

    def test_csp_requires_cash_cover(self):
        arb = RiskArbiter(self.limits)
        prop = self._prop(notional=55_000, strategy="cash_secured_put")
        accepted, _ = arb.check(prop, {"equity": 100_000}, cash=50_000)
        self.assertFalse(accepted)

    def test_oversized_premium_blocked(self):
        arb = RiskArbiter(self.limits)
        # premium = qty x price = 100 contracts x 3000 = 300k > 2% of 100k
        prop = strat.OrderProposal("x", "S", "U", "buy_to_open", 100, 3000.0,
                                   0.1, 21, 0.5, 1_000_000)
        accepted, _ = arb.check(prop, {"equity": 100_000}, cash=10_000_000)
        self.assertFalse(accepted)

    def test_min_premium_floor_blocks_dust(self):
        arb = RiskArbiter(self.limits)
        # premium = 1 x 0.80 = $0.80 < $1 minimum order floor
        prop = strat.OrderProposal("x", "S", "U", "buy_to_open", 1, 0.80,
                                   0.1, 21, 0.5, 100.0)
        accepted, reason = arb.check(prop, {"equity": 100_000}, cash=80_000)
        self.assertFalse(accepted)
        self.assertIn("floor", reason)

    def test_per_leg_premium_cap_blocks_over_500(self):
        arb = RiskArbiter(self.limits)
        # premium = 2 x 300 = $600 > $500 per-leg cap (still < 2% equity)
        prop = strat.OrderProposal("x", "S", "U", "buy_to_open", 2, 300.0,
                                   0.1, 21, 0.5, 100_000.0)
        accepted, reason = arb.check(prop, {"equity": 100_000}, cash=80_000)
        self.assertFalse(accepted)
        self.assertIn("per-leg cap", reason)

    def test_premium_floor_boundary_accepted(self):
        arb = RiskArbiter(self.limits)
        # premium exactly $1.00 -> at floor, accepted
        prop = self._prop()   # qty 1 x price 1.0 = $1.00
        accepted, _ = arb.check(prop, {"equity": 100_000}, cash=80_000)
        self.assertTrue(accepted)

    def test_net_delta_cap_blocks_at_cap(self):
        arb = RiskArbiter(self.limits)
        prop = self._prop()
        # Book already at the ±0.30 net-delta cap -> no new option exposure.
        accepted, reason = arb.check(prop, {"equity": 100_000}, cash=80_000,
                                     net_delta=0.30)
        self.assertFalse(accepted)
        self.assertIn("net delta", reason)

    def test_net_delta_under_cap_allows(self):
        arb = RiskArbiter(self.limits)
        prop = self._prop()
        accepted, _ = arb.check(prop, {"equity": 100_000}, cash=80_000,
                                net_delta=0.15)
        self.assertTrue(accepted)

    def test_bootstrap_builder_prices_notional(self):
        prop = strat.buy_underlying("IWM", 200.0)
        self.assertEqual(prop.strategy, "equity_bootstrap")
        self.assertEqual(prop.side, "buy")
        self.assertEqual(prop.qty, 100)
        self.assertAlmostEqual(prop.notional, 20_000.0)

    def test_normal_proposal_accepted(self):
        arb = RiskArbiter(self.limits)
        accepted, reason = arb.check(self._prop(notional=1500),
                                     {"equity": 100_000}, cash=80_000)
        self.assertTrue(accepted)

    def test_daily_loss_circuit(self):
        arb = RiskArbiter(self.limits)
        self.assertTrue(arb.daily_loss_halted(100_000, 96_900))   # -3.1%
        self.assertFalse(arb.daily_loss_halted(100_000, 97_500))  # -2.5%


class TestSpreadFilter(unittest.TestCase):
    def setUp(self):
        self.limits = config.RiskLimits()

    def test_wide_spread_rejected(self):
        c = make_contract(560, True, oi=500, dte=21)
        c.bid, c.ask, c.mid = 1.00, 1.30, 1.15   # spread 0.30 > 0.15
        self.assertGreater(c.spread, self.limits.max_spread)
        self.assertFalse(opt.passes_screen(c, self.limits))

    def test_narrow_spread_accepted(self):
        c = make_contract(560, True, oi=500, dte=21)
        c.bid, c.ask, c.mid = 2.00, 2.10, 2.05   # spread 0.10
        self.assertLessEqual(c.spread, self.limits.max_spread)
        self.assertTrue(opt.passes_screen(c, self.limits))

    def test_low_open_interest_rejected(self):
        c = make_contract(560, True, oi=10, dte=21)   # OI below 100
        self.assertFalse(opt.passes_screen(c, self.limits))


class TestStrategies(unittest.TestCase):
    def test_covered_call_requires_shares(self):
        prop = strat.covered_call(0, [], 100_000, config.RiskLimits(), 560.0)
        self.assertIsNone(prop)   # no held shares -> no trade

    def test_covered_call_sized_to_shares(self):
        chain = [make_contract(570, True, dte=21)]   # OTM call, shares held
        prop = strat.covered_call(300, chain, 100_000, config.RiskLimits(), 560.0)
        self.assertIsNotNone(prop)
        self.assertLessEqual(prop.qty * 100, 300)   # can't cover more than shares

    def test_cash_secured_put_capped_by_cash(self):
        chain = [make_contract(555, False, dte=21)]
        prop = strat.cash_secured_put(chain, 100_000, 10_000, config.RiskLimits())
        if prop is not None:
            self.assertLessEqual(prop.notional, 10_000)
            self.assertLessEqual(prop.notional, 100_000 * 0.02)


class TestEquitySeed(unittest.TestCase):
    def test_bootstrap_buys_cheapest_when_flat(self):
        # Fresh paper account: no shares anywhere -> buy one IWM lot
        # (cheapest affordable scan underlying) to enable covered calls.
        client = MockClient(equity=100_000, today=TODAY)
        client.set_shares("SPY", 0)
        client.set_shares("QQQ", 0)
        client.set_shares("IWM", 0)
        client.set_cash(80_000)
        agent = Agent(client=client, db_path=":memory:")
        try:
            decisions = agent.run_cycle()
            seeds = [d for d in decisions if d["strategy"] == "equity_bootstrap"]
            self.assertEqual(len(seeds), 1)
            self.assertEqual(seeds[0]["symbol"], "IWM")
            self.assertEqual(seeds[0]["qty"], 100)
            self.assertEqual(client._shares["IWM"], 100)
            self.assertAlmostEqual(client._cash, 80_000 - 100 * 200.0)
        finally:
            agent.close()

    def test_bootstrap_skips_when_shares_held(self):
        # Already seeded (or holding from a prior cycle) -> no bootstrap.
        client = MockClient(equity=100_000, today=TODAY)
        client.set_shares("SPY", 200)
        client.set_cash(80_000)
        agent = Agent(client=client, db_path=":memory:")
        try:
            decisions = agent.run_cycle()
            self.assertNotIn(
                "equity_bootstrap", [d["strategy"] for d in decisions])
        finally:
            agent.close()

    def test_wheel_two_cycles_bootstrap_then_covered_call(self):
        # Cycle 1: flat account -> buy IWM lot. Cycle 2: hold 100 shares ->
        # sell a covered call against them (the Options & Equities wheel).
        client = MockClient(equity=100_000, today=TODAY)
        client.set_shares("SPY", 0)
        client.set_shares("QQQ", 0)
        client.set_shares("IWM", 0)
        client.set_cash(80_000)
        agent = Agent(client=client, db_path=":memory:")
        try:
            d1 = agent.run_cycle()
            seeds = [d for d in d1 if d["strategy"] == "equity_bootstrap"]
            self.assertEqual(len(seeds), 1)
            self.assertEqual(seeds[0]["symbol"], "IWM")
            # Cycle 2: equity held -> covered-call lane live; no re-seed.
            d2 = agent.run_cycle()
            ccs = [d for d in d2 if d["strategy"] == "covered_call"]
            self.assertEqual(len(ccs), 1)
            self.assertTrue(ccs[0]["symbol"].startswith("IWM"))
            self.assertEqual(ccs[0]["qty"], 1)  # 100 shares -> 1 contract
            self.assertNotIn("equity_bootstrap",
                             [d["strategy"] for d in d2])
        finally:
            agent.close()


    def test_bootstrap_skips_when_none_affordable(self):
        # Tiny account: even the IWM lot (100 x 200 = $20k) exceeds 40%.
        client = MockClient(equity=10_000, today=TODAY)
        client.set_shares("SPY", 0)
        client.set_shares("QQQ", 0)
        client.set_shares("IWM", 0)
        client.set_cash(8_000)
        agent = Agent(client=client, db_path=":memory:")
        try:
            decisions = agent.run_cycle()
            self.assertNotIn(
                "equity_bootstrap", [d["strategy"] for d in decisions])
            self.assertEqual(client._shares["IWM"], 0)
        finally:
            agent.close()


class TestAgentCycle(unittest.TestCase):
    def test_cycle_executes_and_logs(self):
        client = MockClient(equity=100_000, today=TODAY)
        client.set_shares("SPY", 300)
        client.set_cash(80_000)
        agent = Agent(client=client, db_path=":memory:")
        try:
            decisions = agent.run_cycle()
            self.assertIsInstance(decisions, list)
        finally:
            agent.close()



    def test_circuit_breaker_flattens_at_deep_drawdown(self):
        # Demo step 5 integration pin: force a >-10% drawdown from the equity
        # high-water mark and watch the agent go FLAT (trailing circuit-breaker
        # through the real run_cycle path, not just arbiter math).
        client = MockClient(equity=100_000, today=TODAY)
        client.set_shares("SPY", 300)
        client.set_cash(80_000)
        agent = Agent(client=client, db_path=":memory:")
        try:
            # Establish the high-water mark with a normal cycle.
            agent.run_cycle()
            self.assertEqual(agent.arbiter.equity_high, 100_000.0)
            # -10.5% from high-water => forced flatten + halt.
            client.set_equity(89_500)
            decisions = agent.run_cycle()
            self.assertEqual(decisions[0]["action"], "FLATTEN")
            self.assertIn("circuit breaker", decisions[0]["reason"])
            flattens = [o for o in client.orders if o.get("action") == "FLATTEN"]
            self.assertEqual(len(flattens), 1)
            # Recovery above the high-water mark re-arms the agent.
            client.set_equity(105_000)
            decisions = agent.run_cycle()
            self.assertNotIn("FLATTEN", [d["action"] for d in decisions])
        finally:
            agent.close()

if __name__ == "__main__":
    unittest.main()
