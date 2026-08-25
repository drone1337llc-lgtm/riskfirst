#!/usr/bin/env python3
"""RiskFirst — P&L export for submission.

Reads state/paper/decisions.db (decisions + account_snapshot tables) and
writes an honest P&L report (markdown) + stats (JSON) for the submission kit.

Usage:
  python3 export_pnl.py [--db PATH] [--out PATH] [--json PATH] [--mode MOCK|PAPER]

Stdlib only. Safe on empty DBs (mock/pre-keys state).
"""
import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone

DEFAULT_DB = os.path.expanduser("~/cryptobot-train/state/paper/decisions.db")

# decisions table column order (id, ts, strategy, symbol, side, qty, price,
# delta, dte, iv_rank, notional, accepted, reason)
I_TS, I_STRAT, I_SYM, I_SIDE = 1, 2, 3, 4
I_QTY, I_PRICE, I_ACCEPTED = 5, 6, 11


def fmt_pct(x):
    return f"{x * 100:.2f}%"


def load(db_path):
    """Return (snapshots, decisions) from the audit DB. Empty tuples if missing."""
    if not os.path.exists(db_path):
        return [], []
    db = sqlite3.connect(db_path)
    try:
        snap = db.execute(
            "select ts, equity, cash, net_delta from account_snapshot order by ts"
        ).fetchall()
        dec = db.execute(
            "select id, ts, strategy, symbol, side, qty, price, delta, dte, "
            "iv_rank, notional, accepted, reason from decisions order by ts"
        ).fetchall()
    finally:
        db.close()
    return snap, dec


def max_drawdown(curve):
    """curve: list of (ts, equity). Returns (max_dd, peak_ts, trough_ts)."""
    if len(curve) < 2:
        return 0.0, None, None
    peak = curve[0]
    max_dd = 0.0
    peak_ts = trough_ts = None
    for ts, eq in curve:
        if eq > peak[1]:
            peak = (ts, eq)
        if peak[1] > 0:
            dd = (peak[1] - eq) / peak[1]
            if dd > max_dd:
                max_dd = dd
                peak_ts, trough_ts = peak[0], ts
    return max_dd, peak_ts, trough_ts


def main():
    ap = argparse.ArgumentParser(description="RiskFirst P&L export")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--out", default=os.path.expanduser(
        "~/cryptobot-train/state/paper/pnl_report.md"))
    ap.add_argument("--json", default=os.path.expanduser(
        "~/cryptobot-train/state/paper/pnl_stats.json"))
    ap.add_argument("--mode", default="PAPER",
                    help="MOCK or PAPER (label only; data is data)")
    args = ap.parse_args()

    snap, dec = load(args.db)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    stats = {
        "generated_at": now,
        "mode": args.mode,
        "n_snapshots": len(snap),
        "n_decisions": len(dec),
        "n_accepted": sum(1 for d in dec if d[I_ACCEPTED]),
        "n_rejected": sum(1 for d in dec if not d[I_ACCEPTED]),
    }

    if snap:
        start_eq = snap[0][1]
        end_eq = snap[-1][1]
        ret = (end_eq - start_eq) / start_eq if start_eq else 0.0
        dd, dd_peak, dd_trough = max_drawdown([(s[0], s[1]) for s in snap])
        stats.update({
            "start_equity": start_eq,
            "end_equity": end_eq,
            "total_return_pct": round(ret * 100, 2),
            "max_drawdown_pct": round(dd * 100, 2),
            "max_dd_peak_ts": dd_peak,
            "max_dd_trough_ts": dd_trough,
        })
    else:
        start_eq = end_eq = None
        ret = dd = 0.0
        dd_peak = dd_trough = None

    strat_counts = {}
    for d in dec:
        s = d[I_STRAT] or "unknown"
        strat_counts[s] = strat_counts.get(s, 0) + 1

    with open(args.out, "w") as f:
        f.write("# RiskFirst — P&L Report\n\n")
        f.write(f"_Generated {now} ({args.mode} mode label) from "
                f"`state/paper/decisions.db` via `export_pnl.py`._\n\n")
        f.write("## Account\n\n")
        if snap:
            f.write(f"- Start equity: **${start_eq:,.2f}**\n")
            f.write(f"- End equity: **${end_eq:,.2f}**\n")
            f.write(f"- Total return: **{fmt_pct(ret)}**\n")
            f.write(f"- Max drawdown: **{fmt_pct(dd)}** "
                    f"(peak {dd_peak} → trough {dd_trough})\n")
            f.write(f"- Snapshot points: {len(snap)}\n")
        else:
            f.write("- No account snapshots yet.\n")
        f.write("\n## Decisions\n\n")
        f.write(f"- Total: {len(dec)} (accepted {stats['n_accepted']}, "
                f"rejected {stats['n_rejected']})\n")
        f.write("- By strategy: " + (
            ", ".join(f"{k} x{v}" for k, v in sorted(strat_counts.items()))
            or "none") + "\n")
        f.write("\n## Equity curve\n\n")
        if snap:
            f.write("| ts | equity |\n|---|---|\n")
            for ts, eq, *_ in snap[-200:]:
                f.write(f"| {ts} | {eq:,.2f} |\n")
        else:
            f.write("_None yet._\n")
        f.write("\n---\n_No live keys are ever read by this script. "
                "Data shown is exactly what is in the audit DB._\n")

    with open(args.json, "w") as f:
        json.dump(stats, f, indent=2, default=str)

    print(json.dumps(stats, indent=2, default=str))


if __name__ == "__main__":
    main()
