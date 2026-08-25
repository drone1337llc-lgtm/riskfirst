"""Alpaca options layer.

Provides a clean, testable interface for:
  * Black-Scholes Greeks computed locally (no external pricing API).
  * Contract list/scan for /v2/options/contracts (SPY/QQQ).
  * Filtering by IV rank, minimum open interest, and max bid/ask spread.

The client adapter (client.py) supplies raw quote/contract data; this module
turns it into decision-ready Option objects.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from statistics import NormalDist
from typing import Callable, Iterable, Optional

from . import config

# Standard normal CDF/PDF (local, dependency-free).
_NORMAL = NormalDist()


def norm_cdf(x: float) -> float:
    return _NORMAL.cdf(x)


def norm_pdf(x: float) -> float:
    return _NORMAL.pdf(x)


# --------------------------------------------------------------------------- #
# Black-Scholes Greeks (European-style approximation, fine for equity options).
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Greeks:
    """Computed Black-Scholes option Greeks."""
    delta: float
    gamma: float
    theta: float      # per day (negative for long premium)
    vega: float
    rho: float
    iv: float


def black_scholes(
    S: float,          # underlying spot
    K: float,          # strike
    T: float,          # time to expiry in years
    r: float,          # risk-free rate (annual, e.g. 0.05)
    sigma: float,      # implied vol (annual), e.g. 0.25
    is_call: bool,
) -> float:
    """Return option theoretical price (Black-Scholes)."""
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if is_call:
        return S * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
    return K * math.exp(-r * T) * norm_cdf(-d2) - S * norm_cdf(-d1)


def greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    is_call: bool,
) -> Greeks:
    """Black-Scholes Greeks in standard units."""
    if T <= 0 or sigma <= 0:
        return Greeks(0.0, 0.0, 0.0, 0.0, 0.0, sigma)
    sqT = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqT)
    d2 = d1 - sigma * sqT
    pdf = norm_pdf(d1)
    delta = norm_cdf(d1) if is_call else norm_cdf(d1) - 1.0
    gamma = pdf / (S * sigma * sqT)
    # Theta: per-year then /365 for per-day; signs per convention (long side).
    theta_year = -(S * pdf * sigma) / (2 * sqT)
    if not is_call:
        theta_year += r * K * math.exp(-r * T) * norm_cdf(-d2)
    else:
        theta_year -= r * K * math.exp(-r * T) * norm_cdf(d2)
    vega = S * pdf * sqT / 100.0
    rho = (
        K * T * math.exp(-r * T) * norm_cdf(d2) / 100.0
        if is_call
        else -K * T * math.exp(-r * T) * norm_cdf(-d2) / 100.0
    )
    return Greeks(delta, gamma, theta_year / 365.0, vega, rho, sigma)


def implied_vol(
    S: float,
    K: float,
    T: float,
    r: float,
    market_price: float,
    is_call: bool,
    tol: float = 1e-6,
    max_iter: int = 100,
) -> Optional[float]:
    """Bisection solve for implied volatility implied by market_price."""
    if market_price <= 0 or T <= 0 or S <= 0:
        return None
    lo, hi = 1e-4, 5.0
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        p = black_scholes(S, K, T, r, mid, is_call)
        if abs(p - market_price) < tol:
            return mid
        if p < market_price:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# --------------------------------------------------------------------------- #
# Option model
# --------------------------------------------------------------------------- #
@dataclass
class Option:
    """A single screened, decision-ready option contract."""
    symbol: str
    underlying: str
    strike: float
    expiry: date
    is_call: bool
    bid: float
    ask: float
    mid: float
    open_interest: int
    spot: float
    dte: int = 0
    iv: float = 0.0
    g: Optional[Greeks] = None
    iv_rank: float = 0.0          # 0..1 percentile rank of current IV
    score: float = 0.0            # strategy-specific attractiveness

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def delta(self) -> float:
        return self.g.delta if self.g else 0.0

    @property
    def notional(self) -> float:
        """Notional capital at risk for 1 contract (100 sh * strike)."""
        return 100.0 * self.strike

    def is_short(self) -> bool:
        """Short (sell-side) position: short call (delta<0) or short put (delta>0)."""
        if not self.g:
            return False
        if self.is_call:
            return self.delta < 0
        return self.delta > 0


def mid_price(bid: float, ask: float) -> float:
    return 0.5 * (bid + ask)


def days_to_expiry(expiry: date, today: Optional[date] = None) -> int:
    today = today or date.today()
    return max(0, (expiry - today).days)


# --------------------------------------------------------------------------- #
# Screening / filtering
# --------------------------------------------------------------------------- #
def passes_screen(opt: Option, limits: config.RiskLimits) -> bool:
    """Apply the risk screens to a single option. Pure + testable."""
    if opt.open_interest < limits.min_open_interest:
        return False
    if opt.spread > limits.max_spread:
        return False
    if not (limits.min_dte <= opt.dte <= limits.max_dte):
        return False
    if opt.iv_rank < limits.min_iv_rank:
        return False
    return True


def rank_contracts(
    contracts: Iterable[Option],
    limits: config.RiskLimits,
    key: Callable[[Option], float] | None = None,
) -> list[Option]:
    """Screen and sort contracts best-first by `key` (default score desc)."""
    screened = [c for c in contracts if passes_screen(c, limits)]
    key = key or (lambda o: o.score)
    screened.sort(key=key, reverse=True)
    return screened


def scan_chain(contracts: Iterable[Option]) -> dict[str, list[Option]]:
    """Group contracts by underlying symbol."""
    out: dict[str, list[Option]] = {}
    for c in contracts:
        out.setdefault(c.underlying, []).append(c)
    return out
