"""Tests for the paper-lane runner (options/options/runner.py).

Offline: no network, no keys. Covers the market-hours gate, session-state
recovery from the audit trail, the mode gate (ALPACA_IS_LIVE + keys), and a
full mock cycle through main().
"""
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from options import runner  # noqa: E402

try:
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    NY = None

pytestmark = pytest.mark.skipif(NY is None, reason="zoneinfo unavailable")


# --------------------------------------------------------------------------- #
# Market-hours gate
# --------------------------------------------------------------------------- #
def test_market_hours_midday_tuesday():
    assert runner.in_market_hours(datetime(2026, 8, 25, 10, 30, tzinfo=NY))


def test_market_hours_weekend_false():
    assert not runner.in_market_hours(datetime(2026, 8, 29, 10, 30, tzinfo=NY))


def test_market_hours_pre_open_false():
    assert not runner.in_market_hours(datetime(2026, 8, 25, 8, 0, tzinfo=NY))


def test_market_hours_post_close_false():
    assert not runner.in_market_hours(datetime(2026, 8, 25, 16, 1, tzinfo=NY))


# --------------------------------------------------------------------------- #
# Session recovery from the audit trail
# --------------------------------------------------------------------------- #
def test_recover_session(tmp_path):
    db = tmp_path / "decisions.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE account_snapshot (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " ts TEXT NOT NULL, equity REAL, cash REAL, net_delta REAL)"
    )
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    today = datetime.now().isoformat()
    con.executemany(
        "INSERT INTO account_snapshot (ts, equity, cash, net_delta) VALUES (?,?,?,?)",
        [(yesterday, 90_000.0, 70_000.0, 0.0),
         (today, 95_000.0, 75_000.0, 0.0),
         (today, 96_000.0, 76_000.0, 0.0)],
    )
    con.commit()
    con.close()

    day_start, high = runner.recover_session(db)
    assert day_start == 95_000.0          # first snapshot of today
    assert high == 96_000.0               # all-time high


def test_recover_session_empty(tmp_path):
    assert runner.recover_session(tmp_path / "nope.db") == (None, 0.0)


# --------------------------------------------------------------------------- #
# Mode/keys gate (main returns 2 before any MCP/Mock work)
# --------------------------------------------------------------------------- #
def test_main_requires_keys(monkeypatch):
    for k in ("ALPACA_API_KEY", "ALPACA_SECRET_KEY", "ALPACA_IS_LIVE",
              "ALPACA_REAL_TRADING"):
        monkeypatch.delenv(k, raising=False)
    assert runner.main(["--once"]) == 2


def test_main_requires_live_flag(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "PKDUMMY00000000000000")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "dummysecret123")
    monkeypatch.delenv("ALPACA_IS_LIVE", raising=False)
    monkeypatch.delenv("ALPACA_REAL_TRADING", raising=False)
    assert runner.main(["--once"]) == 2


def test_main_refuses_real_trading(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "PKDUMMY00000000000000")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "dummysecret123")
    monkeypatch.setenv("ALPACA_IS_LIVE", "1")
    monkeypatch.setenv("ALPACA_REAL_TRADING", "1")
    with pytest.raises(RuntimeError, match="forbidden"):
        runner.main(["--once", "--force"])


# --------------------------------------------------------------------------- #
# Full mock cycle end-to-end (writes state/paper/status.json, gitignored)
# --------------------------------------------------------------------------- #
def test_mock_cycle_once(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    monkeypatch.delenv("ALPACA_IS_LIVE", raising=False)
    monkeypatch.delenv("ALPACA_REAL_TRADING", raising=False)
    assert runner.main(["--mock", "--once", "--force"]) == 0
    status = runner.STATUS_PATH
    assert status.exists()
    import json
    payload = json.loads(status.read_text())
    assert payload["mode"] == "MOCK"
    assert payload["account"]["equity"] == 100_000.0
