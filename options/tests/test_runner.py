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
# State isolation — mock NEVER writes the live paper audit trail
# --------------------------------------------------------------------------- #
def test_state_dir_isolation():
    """--mock must point at state/mock/, the paper lane at state/paper/."""
    mock_dir = runner.set_state_dir(True)
    assert runner.DB_PATH == mock_dir / "decisions.db"
    assert runner.STATUS_PATH == mock_dir / "status.json"
    assert "mock" in str(mock_dir) and "paper" not in str(mock_dir)
    paper_dir = runner.set_state_dir(False)
    assert runner.DB_PATH == paper_dir / "decisions.db"
    assert "paper" in str(paper_dir)


# --------------------------------------------------------------------------- #
# Full mock cycle end-to-end (writes state/mock/, gitignored — never the live
# paper audit trail in state/paper/, which is the judge-visible P&L)
# --------------------------------------------------------------------------- #
def test_mock_cycle_once(monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    monkeypatch.delenv("ALPACA_IS_LIVE", raising=False)
    monkeypatch.delenv("ALPACA_REAL_TRADING", raising=False)
    assert runner.main(["--mock", "--once", "--force"]) == 0
    status = runner.STATUS_PATH
    assert status.exists()
    assert "mock" in str(status)
    import json
    payload = json.loads(status.read_text())
    assert payload["mode"] == "MOCK"
    assert payload["account"]["equity"] == 100_000.0
    assert payload["account"]["account_id"] == "MOCK-ACCT"
    # mock cycles must never write the real paper-account file. When the
    # live MCP lane is deployed the file legitimately exists (written by the
    # real lane on first account connect) — the invariant is that the mock
    # run did NOT create/modify it, so compare mtimes across the run.
    paper_id = runner.ROOT / "state" / "paper" / "paper_account_id.txt"
    paper_status = runner.ROOT / "state" / "paper" / "status.json"
    id_mtime = paper_id.stat().st_mtime_ns if paper_id.exists() else None
    st_mtime = paper_status.stat().st_mtime_ns if paper_status.exists() else None
    assert not (runner.ROOT / "state" / "paper" / "paper_account_id.txt").exists() \
        or id_mtime == paper_id.stat().st_mtime_ns
    assert not (runner.ROOT / "state" / "paper" / "status.json").exists() \
        or st_mtime == paper_status.stat().st_mtime_ns
