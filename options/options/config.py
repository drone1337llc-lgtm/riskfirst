"""Configuration, paper keys, options-level guard, and risk parameters.

Alpaca paper options require "Level 3" on the account. Crypto is spot-only on
Alpaca; options exist only on US equities/ETFs. Paper accounts trade against
simulated fills at mid or limit, never real money — P&L is our judging metric.

Paper keys come from the environment (never committed):
    ALPACA_API_KEY      paper key id
    ALPACA_SECRET_KEY   paper secret

Modes:
    ALPACA_IS_LIVE=1       talk to the REAL Alpaca MCP server — but the
                           server subprocess is hard-forced to ALPACA_PAPER=true
                           (client.py), so this is a *paper* lane, never real.
    ALPACA_REAL_TRADING=1  FORBIDDEN. validate_paper_config() refuses it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Shared state dir for the paper lane (audit trail + runner status).
STATE_DIR: Path = Path(__file__).resolve().parents[2] / "state" / "paper"

# --------------------------------------------------------------------------- #
# Risk parameters — hard gates enforced by the risk arbiter in agent.py.
# --------------------------------------------------------------------------- #

# Equity fractions (0.02 == 2% of buying power/equity).
MAX_PCT_PER_TRADE: float = 0.02          # max 2% equity per trade
DAILY_LOSS_CIRCUIT: float = 0.03         # -3% intraday => flatten & halt new
DRAWDOWN_PAUSE: float = 0.08             # -8% from equity high => pause
CIRCUIT_BREAKER: float = 0.10            # -10% trailing from equity high => flatten & halt
NET_DELTA_CAP: float = 0.30              # net portfolio delta cap (±0.30)

# Contract screening filters.
MIN_OPEN_INTEREST: int = 100             # skip illiquid contracts
MAX_BID_ASK_SPREAD: float = 0.15         # reject options wider than $0.15
MIN_IV_RANK: float = 0.30                # only act when IV rank is elevated
MIN_DTE: int = 7                         # no same-week gamma roulette
MAX_DTE: int = 60                        # cap horizon
TARGET_DTE: int = 21                     # preferred theta harvest horizon
DELTA_SHORT: float = 0.25                # short strike delta target (abs)

# Which underlyings we scan (US equities/ETFs with deep options markets).
SCAN_UNDERLYINGS: tuple[str, ...] = ("SPY", "QQQ")

# Portfolio guardrails.
MAX_PORTFOLIO_WEIGHT_OPTIONS: float = 0.30  # options not >30% of equity
CASH_RESERVE_PCT: float = 0.10              # keep 10% cash buffer minimum


@dataclass(frozen=True)
class RiskLimits:
    """Immutable risk profile, read by the arbiter and the tests."""
    max_position_pct: float = MAX_PCT_PER_TRADE
    daily_loss_circuit: float = DAILY_LOSS_CIRCUIT
    drawdown_pause: float = DRAWDOWN_PAUSE
    circuit_breaker: float = CIRCUIT_BREAKER
    net_delta_cap: float = NET_DELTA_CAP
    min_open_interest: int = MIN_OPEN_INTEREST
    max_spread: float = MAX_BID_ASK_SPREAD
    min_iv_rank: float = MIN_IV_RANK
    min_dte: int = MIN_DTE
    max_dte: int = MAX_DTE
    target_dte: int = TARGET_DTE
    delta_short: float = DELTA_SHORT


def options_level() -> int:
    """Return the account options trading level (0=disabled .. 3=max).

    The real value comes from the live account object; here we default to the
    hackathon-required Level 3 and allow env override for tests.
    """
    return int(os.environ.get("ALPACA_OPTIONS_LEVEL", "3"))


def require_level_3() -> None:
    """Raise if the account is not cleared for paper options (Level 3)."""
    lvl = options_level()
    if lvl < 3:
        raise RuntimeError(
            f"Options trading requires Level 3 clearance on Alpaca paper; "
            f"account level is {lvl}. Enable Level 3 in Alpaca settings."
        )


def live_mode() -> bool:
    """Whether to talk to the real Alpaca MCP server (paper-forced inside).

    ALPACA_IS_LIVE=1 selects McpClient. The server subprocess env pins
    ALPACA_PAPER=true (client.py), so this lane is paper-only no matter
    which keys are set.
    """
    return os.environ.get("ALPACA_IS_LIVE", "0") == "1"


def keys() -> tuple[str, str]:
    """Return (api_key, secret_key) from env or empty strings."""
    return (
        os.environ.get("ALPACA_API_KEY", ""),
        os.environ.get("ALPACA_SECRET_KEY", ""),
    )


def validate_paper_config() -> None:
    """Fail fast if real-money trading is explicitly requested.

    The hackathon is paper-only. ALPACA_IS_LIVE=1 is FINE — it selects the
    MCP lane whose server subprocess is hard-forced to ALPACA_PAPER=true.
    ALPACA_REAL_TRADING=1 is the only setting refused here; combined with
    the client-side paper pin it makes accidental real orders impossible.
    """
    if os.environ.get("ALPACA_REAL_TRADING", "0") == "1":
        raise RuntimeError(
            "ALPACA_REAL_TRADING=1 is forbidden. "
            "Paper-only hackathon — P&L is judged on paper fills "
            "(ALPACA_PAPER=true is pinned inside the MCP lane)."
        )
    require_level_3()
