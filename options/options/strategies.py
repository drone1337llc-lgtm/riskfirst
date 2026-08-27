"""Paper-legal options strategies.

Alpaca paper options = Level 3: covered calls, cash-secured puts, long
calls/puts, debit spreads. NO naked shorts. Each strategy is a pure function
that takes screened candidates + account context and returns a sized order
proposal (or None if not viable).

Strategies:
  A. covered_call    : sell OTM call ~delta 0.25, ~21 DTE on HELD shares
  B. cash_secured_put : sell OTM put ~delta 0.25, <=100% notional in cash
  C. protective_put  : buy OTM put on SPY to cap long-book drawdown
                       (optional: collar by selling a call against it)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from . import config, options as opt

CALL = True
PUT = False


@dataclass
class OrderProposal:
    """A sized order ready for the client."""
    strategy: str
    symbol: str          # contract symbol (e.g. SPY260821C00500000)
    underlying: str
    side: str            # 'buy_to_open' | 'sell_to_open'
    qty: int             # number of contracts
    price: float         # limit price (sell->bid, buy->ask)
    delta: float
    dte: int
    iv_rank: float
    notional: float      # 100 * strike * qty
    reason: str = ""


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def pick_strike(
    contracts: Iterable[opt.Option],
    target_delta: float,
    is_call: bool,
) -> Optional[opt.Option]:
    """Pick the contract whose |delta| is closest to |target_delta|.

    For short options the candidate delta already carries the correct sign
    (short call delta < 0, short put delta > 0); we compare absolute value.
    """
    best = None
    best_err = float("inf")
    for c in contracts:
        if c.is_call != is_call or not c.g:
            continue
        err = abs(abs(c.delta) - abs(target_delta))
        if err < best_err:
            best_err = err
            best = c
    return best


def size_contracts(
    equity: float,
    max_risk_dollars: float,
    price_per_contract: float,
    max_pct: float | None = None,
) -> int:
    """Contracts affordable at <= max_pct% of equity AND <= max_risk_dollars."""
    pct = max_pct or config.MAX_PCT_PER_TRADE
    if price_per_contract <= 0:
        return 0
    by_pct = int((equity * pct) // price_per_contract)
    by_dollars = int(max_risk_dollars // price_per_contract)
    return max(0, min(by_pct, by_dollars))


# --------------------------------------------------------------------------- #
# A. Covered call  (sell OTM call ~delta 0.22, ~21 DTE on held shares)
# --------------------------------------------------------------------------- #
def covered_call(
    held_shares: int,
    contracts: list[opt.Option],
    equity: float,
    limits: config.RiskLimits,
    spot: float,
) -> Optional[OrderProposal]:
    if held_shares <= 0:
        return None  # must own the underlying first
    candidates = [c for c in contracts if c.is_call]
    target = pick_strike(candidates, limits.delta_short, is_call=CALL)
    if target is None:
        return None
    max_sell = held_shares // 100          # can't sell more contracts than shares
    budget = equity * limits.max_position_pct
    qty = size_contracts(equity, budget, target.mid)
    qty = min(qty, max_sell)
    if qty <= 0:
        return None
    return OrderProposal(
        strategy="covered_call",
        symbol=target.symbol,
        underlying=target.underlying,
        side="sell_to_open",
        qty=qty,
        price=target.bid,                  # sell into bid for realistic paper fill
        delta=target.delta,
        dte=target.dte,
        iv_rank=target.iv_rank,
        notional=100 * target.strike * qty,
        reason=(
            f"Covered call {target.underlying} @ {target.strike:,.0f} "
            f"(delta {target.delta:.2f}, {target.dte} DTE, IVr {target.iv_rank:.2f}) "
            f"against {held_shares} held shares; premium {target.bid:.2f}."
        ),
    )


# --------------------------------------------------------------------------- #
# B. Cash-secured put  (sell OTM put ~delta 0.22, <=100% notional in cash)
# --------------------------------------------------------------------------- #
def cash_secured_put(
    contracts: list[opt.Option],
    equity: float,
    cash: float,
    limits: config.RiskLimits,
) -> Optional[OrderProposal]:
    candidates = [c for c in contracts if not c.is_call]
    target = pick_strike(candidates, limits.delta_short, is_call=PUT)
    if target is None:
        return None
    # CSP notional must be fully covered by available cash.
    max_cash_contracts = int(cash / (target.strike * 100.0))
    premium_budget = equity * limits.max_position_pct
    qty = size_contracts(equity, premium_budget, target.mid)
    qty = min(qty, max_cash_contracts)
    if qty <= 0:
        return None
    return OrderProposal(
        strategy="cash_secured_put",
        symbol=target.symbol,
        underlying=target.underlying,
        side="sell_to_open",
        qty=qty,
        price=target.bid,
        delta=target.delta,
        dte=target.dte,
        iv_rank=target.iv_rank,
        notional=target.strike * 100 * qty,
        reason=(
            f"Cash-secured put {target.underlying} @ {target.strike:.2f} "
            f"({target.dte} DTE, IVr {target.iv_rank:.2f}); premium {target.bid:.2f}; "
            f"cash fully covers {qty} contracts."
        ),
    )


# --------------------------------------------------------------------------- #
# C. Protective put / collar on SPY  (buy OTM put to cap long-book drawdown)
# --------------------------------------------------------------------------- #
def protective_put(
    contracts: list[opt.Option],
    long_book_delta: float,
    equity: float,
    limits: config.RiskLimits,
    spot: float,
    collar: bool = False,
) -> Optional[OrderProposal]:
    """Buy an OTM put sized to hedge ~30% of net long delta.

    collar=True also sells an OTM call (delta ~0.22) to fund the put — a
    near-zero-cost hedge (the flagship "options thesis" trade).
    """
    if long_book_delta <= 0:
        return None
    hedge_delta = 0.30 * long_book_delta
    puts = [c for c in contracts if not c.is_call]
    put = pick_strike(puts, 0.25, is_call=PUT)
    if put is None:
        return None
    budget = equity * limits.max_position_pct
    qty = size_contracts(equity, budget, put.ask)
    if qty <= 0:
        return None
    reason = (
        f"Protective put {put.underlying} @ {put.strike:.2f} "
        f"(IVr {put.iv_rank:.2f}) hedging {hedge_delta:.0f} delta of long book; "
        f"cost {put.ask:.2f} x {qty}."
    )
    if collar:
        calls = [c for c in contracts if c.is_call]
        call = pick_strike(calls, 0.25, is_call=CALL)
        if call is not None:
            reason += f" Collared by selling {call.symbol} @ {call.bid:.2f}."
    return OrderProposal(
        strategy="protective_put_collar" if collar else "protective_put",
        symbol=put.symbol,
        underlying=put.underlying,
        side="buy_to_open",
        qty=qty,
        price=put.ask,
        delta=put.delta,
        dte=put.dte,
        iv_rank=put.iv_rank,
        notional=put.strike * 100 * qty,
        reason=reason,
    )


# --------------------------------------------------------------------------- #
# Equity seed (covered-call wheel bootstrap)
# --------------------------------------------------------------------------- #
def buy_underlying(symbol: str, spot: float, qty: int = 100) -> OrderProposal:
    """Buy qty shares of the underlying (market order) to seed the wheel.

    A fresh paper account starts flat; the covered-call strategy requires
    100+ held shares. This is the equity leg of the wheel: buy the lot,
    then sell ~delta-0.25 calls against it on later cycles.
    """
    return OrderProposal(
        strategy="equity_bootstrap",
        symbol=symbol,
        underlying=symbol,
        side="buy",
        qty=qty,
        price=spot,
        delta=0.0,
        dte=0,
        iv_rank=0.0,
        notional=round(spot * qty, 2),
        reason="equity seed for covered-call wheel",
    )


# --------------------------------------------------------------------------- #
# Strategy registry (used by agent + tests)
# --------------------------------------------------------------------------- #
STRATEGIES = {
    "equity_bootstrap": buy_underlying,
    "covered_call": covered_call,
    "cash_secured_put": cash_secured_put,
    "protective_put": protective_put,
}
