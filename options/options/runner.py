"""Paper-trade loop runner — builds the judge-visible P&L track record.

The Alpaca AI Trading Agents hackathon judges live-paper P&L during
Aug 28 - Sep 4 on a fresh $100k paper account. This runner executes the
options agent's decision cycle against the REAL Alpaca MCP server on a
regular schedule, so a track record accumulates without babysitting.

Safety:
  * ALPACA_PAPER=true is hard-forced inside McpClient's server subprocess
    env (see client.py) — this loop CANNOT touch a real account, even with
    live keys in .env. config.validate_paper_config() additionally refuses
    any explicit ALPACA_REAL_TRADING=1.
  * Market-hours gate: cycles only run Mon-Fri 09:30-16:00 America/New_York
    (equity RTH), so no overnight orders or rejected fills.
  * Daily-loss circuit (-3%) and drawdown pause (-8%) are enforced by the
    risk arbiter every cycle; day-start equity and equity-high are
    recovered from the SQLite audit trail so they survive cron restarts.

Usage (from repo root):
    ALPACA_IS_LIVE=1 cryptobot/.venv/bin/python -m options.runner --once
    ALPACA_IS_LIVE=1 cryptobot/.venv/bin/python -m options.runner           # daemon
    cryptobot/.venv/bin/python -m options.runner --mock --once --force       # dry run

State: state/paper/decisions.db (audit), status.json (last summary),
paper_loop.log (runner log).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sqlite3
import sys
import time
from datetime import datetime, time as dtime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "state" / "paper"
DB_PATH = STATE_DIR / "decisions.db"
STATUS_PATH = STATE_DIR / "status.json"
LOG_PATH = STATE_DIR / "paper_loop.log"

try:
    from zoneinfo import ZoneInfo
    NY = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover — minimal system fallback
    NY = None

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass

from options import agent as agent_mod  # noqa: E402
from options import client as client_mod  # noqa: E402
from options import config  # noqa: E402
from options.client import MCPError  # noqa: E402
from options.llm_referee import LLMReferee  # noqa: E402

log = logging.getLogger("options.runner")


# ---------------------------------------------------------------------------
# Market clock
# ---------------------------------------------------------------------------
def in_market_hours(now: datetime | None = None) -> bool:
    """True on Mon-Fri during 09:30-16:00 America/New_York (equity RTH)."""
    now = now or (datetime.now(NY) if NY else datetime.now())
    if now.weekday() >= 5:
        return False
    return dtime(9, 30) <= now.time() <= dtime(16, 0)


def _to_ny(naive_local: datetime) -> datetime:
    if NY is None:
        return naive_local
    local_tz = datetime.now().astimezone().tzinfo
    return naive_local.replace(tzinfo=local_tz).astimezone(NY)


# ---------------------------------------------------------------------------
# Session state recovered from the audit trail (survives cron restarts)
# ---------------------------------------------------------------------------
def recover_session(db_path: Path) -> tuple[float | None, float]:
    """Return (day_start_equity, equity_high).

    day_start = first equity snapshot of the current NY trading day — the
    baseline for the -3% daily-loss circuit. equity_high = all-time max —
    the baseline for the -8% drawdown pause.
    """
    if not db_path.exists():
        return None, 0.0
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT ts, equity FROM account_snapshot ORDER BY id"
            ).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return None, 0.0
    if not rows:
        return None, 0.0
    today = (datetime.now(NY) if NY else datetime.now()).date()
    day_start, high = None, 0.0
    for ts, eq in rows:
        high = max(high, eq)
        try:
            snap_dt = datetime.fromisoformat(ts)
        except ValueError:
            continue
        if _to_ny(snap_dt).date() == today and day_start is None:
            day_start = eq
    return day_start, high


# ---------------------------------------------------------------------------
# Cycle + status
# ---------------------------------------------------------------------------
def run_cycle(agent: agent_mod.Agent) -> dict:
    """One decision pass with session state carried over from history."""
    day_start, equity_high = recover_session(DB_PATH)
    agent.arbiter.equity_high = max(agent.arbiter.equity_high, equity_high)
    decisions = agent.run_cycle(day_start_equity=day_start)
    return {"ts": datetime.now().isoformat(), "n": len(decisions),
            "decisions": decisions}


def write_status(summary: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(summary, indent=2, default=str))


def make_agent(mock: bool) -> agent_mod.Agent:
    client = client_mod.build_client(live=not mock)
    use_referee = os.environ.get("OLLAMA_REFEREE_DISABLED", "0") != "1"
    referee = LLMReferee() if (use_referee and not mock) else None
    return agent_mod.Agent(client=client, db_path=str(DB_PATH), referee=referee)


def setup_logging() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_PATH)],
    )


def _run_once(agent: agent_mod.Agent, mock: bool) -> dict:
    summary = run_cycle(agent)
    acct = agent.client.get_account()
    summary["account"] = {"equity": acct.get("equity"), "cash": acct.get("cash")}
    summary["mode"] = "MOCK" if mock else "MCP-PAPER"
    write_status(summary)
    log.info("cycle done: %s action(s)", summary["n"])
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--once", action="store_true", help="one cycle, then exit")
    ap.add_argument("--force", action="store_true",
                    help="ignore the market-hours gate")
    ap.add_argument("--interval", type=int, default=300,
                    help="seconds between cycles (daemon mode, default 300)")
    ap.add_argument("--mock", action="store_true",
                    help="MockClient dry-run (key-free, no orders)")
    args = ap.parse_args(argv)

    setup_logging()

    if not args.mock:
        config.validate_paper_config()   # refuses real-money rail; checks L3
        if not config.keys():
            print("ALPACA_API_KEY/ALPACA_SECRET_KEY missing — copy .env.example")
            return 2
        if os.environ.get("ALPACA_IS_LIVE", "0") != "1":
            print("ALPACA_IS_LIVE=1 required for the MCP paper lane")
            return 2

    agent = make_agent(args.mock)

    if args.once:
        try:
            if not args.force and not in_market_hours():
                log.info("outside RTH — skipping")
                return 0
            print(json.dumps(_run_once(agent, args.mock), indent=2, default=str))
            return 0
        except MCPError as exc:
            log.warning("cycle failed (MCP): %s", exc)
            return 1
        finally:
            agent.close()

    # --- daemon loop ------------------------------------------------------- #
    def _stop(signum, frame):  # pragma: no cover
        log.info("signal %s — shutting down", signum)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    try:
        while True:
            if args.force or in_market_hours():
                try:
                    _run_once(agent, args.mock)
                except MCPError as exc:
                    log.warning("cycle failed (MCP): %s", exc)
            else:
                log.info("outside RTH — waiting")
            time.sleep(args.interval)
    finally:  # pragma: no cover
        agent.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
