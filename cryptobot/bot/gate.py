"""OOS hard gate — fail-closed enforcement of the walk-forward crypto gate.

Council verdict (2026-08-24), priority #2: the crypto lane stays ONLY if the
walk-forward out-of-sample Sharpe is positive net. eval_oos.py computes the
verdict; this module is the ENFORCEMENT half — bot/run.py refuses to start
unless the gate passes.

Canonical verdict file: STATE_DIR/eval_oos_full.json (spec-compliant full run,
see README). Fallback: STATE_DIR/eval_oos.json (eval_oos.py default output).
Missing / unreadable / FAIL / non-positive mean Sharpe all FAIL CLOSED — the
crypto lane must never trade on an unproven policy.

The numeric Sharpe is authoritative, not the "verdict" string: the file could
be hand-edited, so a PASS verdict with negative math still closes the gate.
"""
import json
import logging
import os

import config

log = logging.getLogger("gate")

VERDICT_FILES = ("eval_oos_full.json", "eval_oos.json")


def check_oos_gate(state_dir: str | None = None) -> dict:
    """Return the gate verdict.

    Result dict: {ok, verdict, mean_sharpe, file, reason}
      ok          True  -> lane may run
      ok          False -> lane must NOT run (fail closed)
      reason      human-readable explanation when not ok (None when ok)
    """
    state_dir = state_dir or config.STATE_DIR

    for name in VERDICT_FILES:
        path = os.path.join(state_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            return {"ok": False, "verdict": None, "mean_sharpe": None,
                    "file": path, "reason": f"unreadable verdict file: {e}"}
        if not isinstance(data, dict):
            return {"ok": False, "verdict": None, "mean_sharpe": None,
                    "file": path, "reason": "verdict file is not a JSON object"}

        mean = data.get("mean_oos_ann_sharpe")
        if mean is None:
            return {"ok": False, "verdict": data.get("verdict"),
                    "mean_sharpe": None, "file": path,
                    "reason": "verdict file missing mean_oos_ann_sharpe"}
        mean = float(mean)
        if mean > 0:
            return {"ok": True, "verdict": data.get("verdict"),
                    "mean_sharpe": mean, "file": path, "reason": None}
        return {"ok": False, "verdict": data.get("verdict"),
                "mean_sharpe": mean, "file": path,
                "reason": f"OOS mean Sharpe {mean} is not positive net"}

    return {"ok": False, "verdict": None, "mean_sharpe": None, "file": None,
            "reason": f"no OOS verdict file in {state_dir} (run eval_oos.py first)"}
