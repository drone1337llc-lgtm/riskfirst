"""Champion/challenger promote — enforce the README 'only promote on an OOS win' rule.

The crypto lane keeps ONE live champion (config.CHECKPOINT_PATH) that bot/run.py
loads. Training must NEVER silently overwrite the champion: a challenger only
replaces the live lane after winning a walk-forward OOS evaluation, never on
training loss (README 'Risk rails (both lanes)').

Enforce-half of that contract:
  - train.py refuses to write the champion path directly (see check_not_champion).
  - promote_checkpoint() promotes a challenger ONLY when its OOS verdict passes
    (mean_oos_ann_sharpe > 0 from the canonical challenger verdict file) AND it
    beats the incumbent champion's recorded OOS metric. Everything else refuses.

Verdict source for challengers: eval_oos.py --checkpoint writes
state/<SYM>/eval_oos_challenger.json (same shape as the gate file).
Incumbent metric: recorded in state/<SYM>/promote.json at promotion time.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import zipfile

import config

log = logging.getLogger("promote")

CHALLENGER_EVAL_FILE = "eval_oos_challenger.json"
PROMOTE_FILE = "promote.json"

# --- verdict loading (mirrors bot.gate fail-closed shape) -------------------


def load_challenger_verdict(state_dir: str | None = None) -> dict:
    """Read the challenger OOS verdict (fail-closed: same numeric rule as gate).

    Returns {ok, mean_sharpe, file, reason}: ok True iff the challenger's own
    walk-forward mean OOS ann. Sharpe is strictly positive.
    """
    state_dir = state_dir or config.STATE_DIR
    path = os.path.join(state_dir, CHALLENGER_EVAL_FILE)
    if not os.path.isfile(path):
        return {"ok": False, "mean_sharpe": None, "file": path,
                "reason": f"no challenger verdict at {path} (run: python eval_oos.py --checkpoint <model.zip>)"}
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        return {"ok": False, "mean_sharpe": None, "file": path,
                "reason": f"unreadable challenger verdict: {e}"}
    if not isinstance(data, dict):
        return {"ok": False, "mean_sharpe": None, "file": path,
                "reason": "challenger verdict is not a JSON object"}
    mean = data.get("mean_oos_ann_sharpe")
    if mean is None:
        return {"ok": False, "mean_sharpe": None, "file": path,
                "reason": "challenger verdict missing mean_oos_ann_sharpe"}
    mean = float(mean)
    if mean > 0:
        return {"ok": True, "mean_sharpe": mean, "file": path, "reason": None}
    return {"ok": False, "mean_sharpe": mean, "file": path,
            "reason": f"challenger OOS mean Sharpe {mean} is not positive net"}


def _load_promote_record(state_dir: str) -> dict | None:
    path = os.path.join(state_dir, PROMOTE_FILE)
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        log.warning("promote record at %s unreadable; treating as absent", path)
        return None


def _write_promote_record(state_dir: str, champion: str, mean_sharpe: float,
                          challenger_src: str) -> None:
    os.makedirs(state_dir, exist_ok=True)
    from datetime import datetime, timezone
    rec = {
        "champion": champion,
        "mean_oos_ann_sharpe": mean_sharpe,
        "challenger_src": challenger_src,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    with open(os.path.join(state_dir, PROMOTE_FILE), "w") as f:
        json.dump(rec, f, indent=2)


# --- the promote decision -----------------------------------------------------


def check_not_champion(out: str) -> None:
    """Guard: training output may never be the live champion path.

    Raises ValueError when ``out`` resolves to the champion checkpoint, so a
    retrained policy can't clobber the live lane by default or by accident.
    """
    champion = os.path.realpath(config.CHECKPOINT_PATH)
    out_real = os.path.realpath(out)
    if out_real == champion:
        raise ValueError(
            f"refusing to write challenger over the live champion ({config.CHECKPOINT_PATH}). "
            "Train to a challenger path (default), then gate it: "
            "'python eval_oos.py --checkpoint <challenger.zip>' then "
            "'python -m cryptobot.bot.promote --challenger <challenger.zip>'."
        )


def promote_checkpoint(challenger: str, champion: str | None = None,
                       state_dir: str | None = None, force: bool = False) -> dict:
    """Promote a challenger checkpoint to champion — ONLY on a winning OOS verdict.

    Fail-closed rules:
      1. challenger must exist and be a valid .zip checkpoint;
      2. challenger must PASS its walk-forward OOS verdict (mean Sharpe > 0),
         unless ``force`` (operator override);
      3. when an incumbent champion is recorded, the challenger must STRICTLY
         beat the champion's recorded OOS metric (README: 'only replaces the
         live lane on an OOS win, never on training loss');

    On success the challenger atomically replaces the champion checkpoint and
    state/<spec>/promote.json records the new champion + metric.
    """
    champion = champion or config.CHECKPOINT_PATH
    state_dir = state_dir or config.STATE_DIR

    if not os.path.isfile(challenger):
        return {"ok": False, "reason": f"challenger checkpoint not found: {challenger}"}
    if not zipfile.is_zipfile(challenger):
        return {"ok": False, "reason": f"challenger is not a zip checkpoint: {challenger}"}

    verdict = load_challenger_verdict(state_dir)
    if not verdict["ok"] and not force:
        return {"ok": False, "reason": verdict["reason"]}

    mean = verdict["mean_sharpe"] if verdict["ok"] else None
    if not force:
        record = champion_record(state_dir)
        if record is not None and mean <= float(record["mean_oos_ann_sharpe"]):
            return {"ok": False,
                    "reason": (f"challenger OOS Sharpe {mean} does not beat incumbent "
                               f"{record['mean_oos_ann_sharpe']} — champion kept")}

    # Atomic-ish replace: copy to temp then rename so a crash never truncates champion.
    tmp = champion + ".promote-tmp"
    shutil.copy2(challenger, tmp)
    os.replace(tmp, champion)
    if mean is not None:
        _write_promote_record(state_dir, champion, mean, challenger)
    log.info("promoted %s -> %s (mean OOS Sharpe %s)", challenger, champion, mean)
    return {"ok": True, "mean_sharpe": mean, "champion": champion,
            "reason": "promoted on OOS win" if mean is not None else "promoted (force)"}


def champion_record(state_dir: str | None = None) -> dict | None:
    state_dir = state_dir or config.STATE_DIR
    return _load_promote_record(state_dir)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Promote a gated challenger to champion")
    p.add_argument("--challenger", required=True, help="path to challenger .zip checkpoint")
    p.add_argument("--force", action="store_true",
                   help="bypass the OOS-win gate (operator override only)")
    args = p.parse_args()
    res = promote_checkpoint(args.challenger, force=args.force)
    print(json.dumps(res, indent=2))
    raise SystemExit(0 if res.get("ok") else 1)
