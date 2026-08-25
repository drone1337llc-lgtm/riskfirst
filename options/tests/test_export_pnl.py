"""Tests for bin/export_pnl.py — the submission P&L export tool.

Offline, no network, no keys. Uses a temp DB with known fixtures.
"""
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EXPORT = REPO / "bin" / "export_pnl.py"
PY = sys.executable


@pytest.fixture
def tmp_db(tmp_path):
    """Build a small audit DB with 2 snapshots + 3 decisions."""
    db = sqlite3.connect(tmp_path / "decisions.db")
    db.executescript(
        """
        CREATE TABLE decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL, strategy TEXT, symbol TEXT, side TEXT,
            qty INTEGER, price REAL, delta REAL, dte INTEGER,
            iv_rank REAL, notional REAL, accepted INTEGER NOT NULL, reason TEXT
        );
        CREATE TABLE account_snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL, equity REAL, cash REAL, net_delta REAL
        );
        INSERT INTO account_snapshot (ts, equity, cash, net_delta) VALUES
            ('2026-08-25T09:00:00', 100000.0, 100000.0, 0.0),
            ('2026-08-25T10:00:00', 101000.0, 95000.0, 0.2),
            ('2026-08-25T11:00:00', 100500.0, 94000.0, 0.1);
        INSERT INTO decisions (ts, strategy, symbol, side, qty, price, delta,
                               dte, iv_rank, notional, accepted, reason) VALUES
            ('2026-08-25T09:30:00','covered_call','SPY261009C00605000','SELL',2,7.75,0.25,10,0.7,1550,1,'arbiter ok'),
            ('2026-08-25T10:30:00','cash_secured_put','QQQ260915P00461000','SELL',1,3.2,0.2,0,0.6,320,1,'arbiter ok'),
            ('2026-08-25T10:45:00','covered_call','SPY261009C00605000','SELL',1,7.5,0.24,0,0.65,750,0,'delta too high');
        """
    )
    db.close()
    return tmp_path / "decisions.db"


def test_export_report_and_stats(tmp_db, tmp_path):
    out = tmp_path / "pnl_report.md"
    stats = tmp_path / "pnl_stats.json"
    r = subprocess.run(
        [PY, str(EXPORT), "--db", str(tmp_db), "--out", str(out),
         "--json", str(stats), "--mode", "MOCK"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, r.stderr
    assert out.exists()
    assert stats.exists()
    data = json.loads(stats.read_text())
    assert data["n_snapshots"] == 3
    assert data["n_decisions"] == 3
    assert data["n_accepted"] == 2
    assert data["n_rejected"] == 1
    assert data["start_equity"] == 100000.0
    assert data["end_equity"] == 100500.0
    # 100.5k from 100k = +0.5%; peak 101k then trough 100.5k => 0.495% DD
    assert data["total_return_pct"] == 0.5
    assert 0.49 <= data["max_drawdown_pct"] <= 0.5
    md = out.read_text()
    assert "RiskFirst" in md
    assert "covered_call x2" in md
    assert "cash_secured_put x1" in md
    assert "$100,500.00" in md


def test_export_missing_db_ok(tmp_path):
    """A missing DB (pre-keys state) must not crash — empty report."""
    out = tmp_path / "pnl_report.md"
    stats = tmp_path / "pnl_stats.json"
    r = subprocess.run(
        [PY, str(EXPORT), "--db", str(tmp_path / "nope.db"), "--out", str(out),
         "--json", str(stats), "--mode", "MOCK"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(stats.read_text())
    assert data["n_snapshots"] == 0
    assert data["n_decisions"] == 0
