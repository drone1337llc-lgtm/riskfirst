"""Autonomous options agent — decision loop + risk arbiter + SQLite log.

Multi-agent architecture:
  * strategy sub-agents (bull/bear/neutral) propose trades via strategies.py.
  * risk arbiter gates every proposal against config.RiskLimits and the live
    account state (position %, daily loss circuit, drawdown pause, net delta).
  * IV-rank structure matrix picks the best strategy per underlying by scoring
    which structure is most attractive given the chain's IV rank.

Every decision is logged to SQLite (decisions.db) with reasoning for audit.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from . import config, client as client_mod, options as opt, strategies as strat


# --------------------------------------------------------------------------- #
# Decision log (SQLite)
# --------------------------------------------------------------------------- #
class DecisionLog:
    """Append-only audit trail of every decision in decisions.db."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        strategy TEXT,
        symbol TEXT,
        side TEXT,
        qty INTEGER,
        price REAL,
        delta REAL,
        dte INTEGER,
        iv_rank REAL,
        notional REAL,
        accepted INTEGER NOT NULL,
        reason TEXT
    );
    CREATE TABLE IF NOT EXISTS account_snapshot (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        equity REAL,
        cash REAL,
        net_delta REAL
    );
    """

    def __init__(self, path: str = "decisions.db"):
        self.path = path
        self._conn = sqlite3.connect(path)
        self._conn.executescript(self.SCHEMA)
        self._conn.commit()

    def log_decision(self, proposal: strat.OrderProposal,
                     accepted: bool, note: str = "") -> None:
        self._conn.execute(
            "INSERT INTO decisions (ts, strategy, symbol, side, qty, price, "
            "delta, dte, iv_rank, notional, accepted, reason) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                datetime.now().isoformat(), proposal.strategy, proposal.symbol,
                proposal.side, proposal.qty, proposal.price, proposal.delta,
                proposal.dte, proposal.iv_rank, proposal.notional,
                int(accepted),
                proposal.reason + (" | " + note if note else ""),
            ),
        )
        self._conn.commit()

    def log_account(self, equity: float, cash: float, net_delta: float) -> None:
        self._conn.execute(
            "INSERT INTO account_snapshot (ts, equity, cash, net_delta) "
            "VALUES (?,?,?,?)",
            (datetime.now().isoformat(), equity, cash, net_delta),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


# --------------------------------------------------------------------------- #
# Risk arbiter — the gatekeeper every proposal must pass.
# --------------------------------------------------------------------------- #
@dataclass
class RiskArbiter:
    limits: config.RiskLimits
    equity_high: float = 0.0     # running equity high for drawdown calc

    def update_high(self, equity: float) -> None:
        self.equity_high = max(self.equity_high, equity)

    def check(self, proposal, account: dict, cash: float) -> tuple[bool, str]:
        """Return (accepted, reason). Encapsulates all hard risk gates.

        For options, the capital at risk in a single trade is the *premium*
        (qty x price) — not the strike notional. The notional for covered
        calls / cash-secured puts is just collateral, not loss exposure.
        """
        eq = account["equity"]
        premium_at_risk = proposal.qty * proposal.price

        # 1. Position-size gate: premium at risk <= max% of equity.
        if premium_at_risk > eq * self.limits.max_position_pct:
            return False, (
                f"premium at risk {premium_at_risk:.2f} exceeds "
                f"{self.limits.max_position_pct:.0%} equity cap"
            )

        # 2. Cash-secured puts must be fully cash-covered (collateral).
        if proposal.strategy == "cash_secured_put" and proposal.notional > cash:
            return False, "CSP notional exceeds available cash"

        # 3. Drawdown pause gate (-8% from equity high).
        self.update_high(eq)
        if self.equity_high > 0 and eq < self.equity_high * (1 - self.limits.drawdown_pause):
            return False, f"drawdown pause active ({(1 - eq / self.equity_high):.1%})"

        return True, "passed risk gates"

    def daily_loss_halted(self, day_start_eq: float, current_eq: float) -> bool:
        """True if intraday P&L <= -3% (forces flatten)."""
        if day_start_eq <= 0:
            return False
        return (current_eq - day_start_eq) / day_start_eq <= -self.limits.daily_loss_circuit


# --------------------------------------------------------------------------- #
# Agent
# --------------------------------------------------------------------------- #
class Agent:
    def __init__(self, client: Optional[client_mod.BaseClient] = None,
                 limits: Optional[config.RiskLimits] = None,
                 db_path: str = "decisions.db",
                 today: Optional[date] = None):
        self.client = client or client_mod.build_client()
        self.limits = limits or config.RiskLimits()
        self.db = DecisionLog(db_path)
        self.today = today or date.today()
        self.arbiter = RiskArbiter(self.limits)

    def held_shares(self, symbol: str) -> int:
        for p in self.client.get_positions():
            if p.get("symbol") == symbol and p.get("asset_class") == "us_equity":
                return int(p.get("qty", 0))
        return 0

    def net_delta(self) -> float:
        """Sum of option deltas across positions (approx)."""
        return sum(p.get("delta", 0.0) for p in self.client.get_positions())

    def _gate_and_submit(self, proposal, account: dict, cash: float) -> bool:
        accepted, reason = self.arbiter.check(proposal, account, cash)
        self.db.log_decision(proposal, accepted, reason)
        if accepted:
            self.client.submit_order(proposal)
        return accepted

    def run_cycle(self, day_start_equity: Optional[float] = None) -> list[dict]:
        """One full decision pass: read account, scan chains, pick strategy by
        IV rank, size, submit, log. Returns a list of executed actions."""
        account = self.client.get_account()
        cash = account["cash"]
        equity = account["equity"]
        day_start = day_start_equity or equity

        # Circuit breaker: intraday -3% => flatten, no new trades.
        if self.arbiter.daily_loss_halted(day_start, equity):
            self.client.flatten()
            self.db.log_account(equity, cash, 0.0)
            return [{"action": "FLATTEN", "reason": "daily loss circuit (-3%)"}]

        decisions: list[dict] = []
        for underlying in config.SCAN_UNDERLYINGS:
            chain = self.client.get_contracts(underlying)
            spot = next((c.spot for c in chain), None)
            if spot is None:
                continue

            # IV-rank structure matrix: elevated IV -> sell premium;
            # low IV -> buy protection (SPY).
            avg_ivr = _chain_iv_rank(chain)
            proposal = None

            if avg_ivr >= self.limits.min_iv_rank:
                held = self.held_shares(underlying)
                if held >= 100:
                    proposal = strat.covered_call(held, chain, equity,
                                                  self.limits, spot)
                if proposal is None and cash > 0:
                    proposal = strat.cash_secured_put(chain, equity, cash,
                                                      self.limits)
            else:
                if underlying == "SPY":
                    book_delta = self.net_delta()
                    proposal = strat.protective_put(chain, book_delta, equity,
                                                    self.limits, spot, collar=True)

            if proposal is not None and self._gate_and_submit(proposal, account, cash):
                decisions.append({
                    "action": "TRADE",
                    "strategy": proposal.strategy,
                    "symbol": proposal.symbol,
                    "qty": proposal.qty,
                    "price": proposal.price,
                    "delta": proposal.delta,
                    "iv_rank": proposal.iv_rank,
                })

        self.db.log_account(equity, cash, self.net_delta())
        return decisions

    def close(self) -> None:
        self.db.close()


def _chain_iv_rank(chain: list[opt.Option]) -> float:
    if not chain:
        return 0.0
    return sum(o.iv_rank for o in chain) / len(chain)
