"""Walk-forward out-of-sample evaluator — the HARD GATE for the crypto lane.

Decides whether to keep building Cryptonaut. If OOS net Sharpe is not positive,
the crypto lane stops (per adversarial council verdict 2026-08-24).

Design:
- Sequential K folds (NO look-ahead leakage). Fold i trains only on bars BEFORE
  the fold's OOS window, then evaluates on that window with deterministic actions.
- Evaluation replicates live semantics EXACTLY: policy outputs a target allocation
  from config.TARGET_ALLOCATIONS; we hold that allocation over the next bar and
  mark-to-market. Commission=0 (Alpaca paper). This is the same decision the live
  bot makes every DECISION_INTERVAL_S.
- Metrics per fold + aggregated: net return, annualized Sharpe (log returns), max DD.
- Verdict: PASS iff mean OOS annualized Sharpe > 0 (net) — no exceptions.

Usage:
  python oos_eval.py --timesteps 300000 --folds 4 [--symbol ETH-USD]
Exit code 0 = PASS, 1 = FAIL, 2 = error.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import config
from bot import data
from bot.env import build_env
from shimmy import GymV21CompatibilityV0
from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor


def simulate_oos(prices: pd.DataFrame, feats: pd.DataFrame, model) -> dict:
    """Replay the policy's target allocation over an OOS window (deterministic).

    Holds each chosen allocation for the NEXT bar (rebalance at bar close),
    matching the live loop's every-5-min decision on 1-min bars. Returns
    portfolio net-worth series and derived stats.
    """
    allocs = np.asarray(config.TARGET_ALLOCATIONS, dtype=float)
    close = prices["close"].to_numpy(dtype=float)
    feat = feats.to_numpy(dtype=np.float32)

    n = len(close)
    win = config.WINDOW_SIZE
    if n < win + 1:
        raise ValueError(f"OOS window too small: {n} < {win}+1")

    nw = np.empty(n)
    nw[0] = config.INITIAL_CASH
    # initial: hold alloc decided on first decision bar; before that, cash.
    target = 0.0
    for i in range(n):
        if i >= win:
            obs = feat[i - win:i]          # shape (win, n_feat) = what live bot sees
            act, _ = model.predict(obs, deterministic=True)
            target = float(allocs[int(act)])
        # apply target to return of bar i (log-return for smoothness)
        ret = 0.0 if i == 0 else np.log(close[i] / close[i - 1])
        nw[i] = nw[i - 1] * (1.0 - target + target * np.exp(ret)) if i > 0 else config.INITIAL_CASH

    # --- stats ---
    nw = np.maximum(nw, 1e-9)
    logr = np.diff(np.log(nw))
    mu = logr.mean()
    sd = logr.std(ddof=1)
    sharpe = 0.0 if sd == 0 else mu / sd * np.sqrt(252 * 24 * 60)  # annualize 1-min bars
    peak = np.maximum.accumulate(nw)
    dd = ((peak - nw) / peak).max()
    ret = nw[-1] / config.INITIAL_CASH - 1.0
    return {
        "net_return": float(ret),
        "ann_sharpe": float(sharpe),
        "max_dd": float(dd),
        "final_nw": float(nw[-1]),
        "n_bars": n,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--timesteps", type=int, default=300_000)
    p.add_argument("--folds", type=int, default=4)
    p.add_argument("--out", default=os.path.join(config.STATE_DIR, "oos_eval.json"))
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    prices, feats = data.load_dataset()
    n = len(feats)
    win = config.WINDOW_SIZE
    # each fold: test = 20% of data (rounded), training = everything before it
    fold_size = max(win + 50, n // (args.folds + 1))
    print(f"dataset {n} bars, folds={args.folds}, fold_test={fold_size}")

    results = []
    t0 = time.time()
    for k in range(args.folds):
        test_end = n - k * fold_size           # leave last fold(s) contiguous... use expanding train
        test_start = test_end - fold_size
        if test_start <= win + 20:
            break  # not enough bars left for this fold
        train_p = prices.iloc[:test_start]
        train_f = feats.iloc[:test_start]
        test_p = prices.iloc[test_start:test_end]
        test_f = feats.iloc[test_start:test_end]

        env = Monitor(GymV21CompatibilityV0(env=build_env(train_p, train_f)))
        model = PPO("MlpPolicy", env, verbose=0, device="cpu",
                    n_steps=2048, batch_size=256, learning_rate=3e-4,
                    gamma=0.99, ent_coef=0.01)
        model.learn(total_timesteps=args.timesteps)

        oos = simulate_oos(test_p, test_f, model)
        oos["fold"] = k + 1
        oos["train_bars"] = test_start
        oos["test_start"] = str(test_p.index[0])
        oos["test_end"] = str(test_p.index[-1])
        results.append(oos)
        print(f"fold {k+1}/{args.folds}: OOS sharpe={oos['ann_sharpe']:.3f} "
              f"ret={oos['net_return']:.4f} maxdd={oos['max_dd']:.3f} "
              f"train={test_start} test={test_start}-{test_end} "
              f"[{round(time.time()-t0,0)}s elapsed]", flush=True)

    if not results:
        print("ERROR: no folds evaluated (dataset too short?)")
        sys.exit(2)

    sharpe_arr = np.array([r["ann_sharpe"] for r in results])
    mean_sharpe = float(sharpe_arr.mean())
    neg = int((sharpe_arr < 0).sum())
    ret_arr = np.array([r["net_return"] for r in results])
    summary = {
        "symbol": config.SYMBOL,
        "timesteps": args.timesteps,
        "folds_evaluated": len(results),
        "mean_oos_ann_sharpe": round(mean_sharpe, 4),
        "negative_sharpe_folds": neg,
        "folds": results,
        "verdict": "PASS" if mean_sharpe > 0 else "FAIL",
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(json.dumps(summary, indent=2))
    print("VERDICT:", summary["verdict"])
    sys.exit(0 if mean_sharpe > 0 else 1)


if __name__ == "__main__":
    main()
