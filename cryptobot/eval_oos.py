"""Walk-forward out-of-sample evaluator — the HARD GATE for the crypto lane (Sprint A).

Spec (adversarial council verdict 2026-08-24): train on [t-k, t-0.25k], eval on
[t-0.25k, t], roll forward at least 4 folds. Report Sharpe + max drawdown net of
realistic costs. PASS iff mean OOS Sharpe > 0.

Evaluation replicates live semantics: policy outputs a target allocation from
config.TARGET_ALLOCATIONS, held over the next bar, mark-to-market. Commission = 0
(Alpaca paper). This is the same decision the live bot makes every DECISION_INTERVAL_S.

Usage:
  python eval_oos.py --bars 2000 --folds 4 --timesteps 10000   # quick sample
  python eval_oos.py                                           # full gate (default fetch)
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
    """Replay the policy's target allocation over an OOS window (deterministic)."""
    allocs = np.asarray(config.TARGET_ALLOCATIONS, dtype=float)
    close = prices["close"].to_numpy(dtype=float)
    feat = feats.to_numpy(dtype=np.float32)

    n = len(close)
    win = config.WINDOW_SIZE
    if n < win + 1:
        raise ValueError(f"OOS window too small: {n} < {win}+1")

    nw = np.empty(n)
    nw[0] = config.INITIAL_CASH
    target = 0.0
    for i in range(n):
        if i >= win:
            obs = feat[i - win:i]          # shape (win, n_feat) = what live bot sees
            act, _ = model.predict(obs, deterministic=True)
            target = float(allocs[int(act)])
        ret = 0.0 if i == 0 else np.log(close[i] / close[i - 1])
        nw[i] = nw[i - 1] * (1.0 - target + target * np.exp(ret)) if i > 0 else config.INITIAL_CASH

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
    p.add_argument("--bars", type=int, default=0,
                   help="number of bars to fetch; 0 = use config.LOOKBACK_BARS")
    p.add_argument("--folds", type=int, default=4)
    p.add_argument("--timesteps", type=int, default=300_000)
    p.add_argument("--checkpoint", default=None,
                   help="champion/challenger .zip to evaluate OOS (instead of training fresh)")
    p.add_argument("--out", default=None,
                   help="verdict output path (default: state/<SYM>/eval_oos.json, or "
                        "eval_oos_challenger.json when --checkpoint is given)")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    prices, feats = data.load_dataset()
    if args.checkpoint:
        from stable_baselines3 import PPO as _PPO
        challenger_model = _PPO.load(args.checkpoint, device="cpu")
        print(f"gating checkpoint: {args.checkpoint}")
    out_path = args.out or (
        os.path.join(config.STATE_DIR, "eval_oos_challenger.json")
        if args.checkpoint else os.path.join(config.STATE_DIR, "eval_oos.json"))
    if args.bars and args.bars > 0:
        prices = prices.iloc[-args.bars:]
        feats = feats.iloc[-args.bars:]
    n = len(feats)
    win = config.WINDOW_SIZE

    # Spec: each fold has a total window of length k = 4*eval_chunk.
    # train = first 75% of the window ([t-k, t-0.25k]), eval = last 25% ([t-0.25k, t]).
    # Roll forward so the last eval chunk ends at the dataset end.
    # eval_chunk must be >= WINDOW_SIZE+1 so simulate_oos can build the final
    # observation window; cap it so the requested fold count fits in the dataset
    # (oldest fold's train start must leave >= WINDOW_SIZE warmup bars).
    min_chunk = win + 1
    desired = max(min_chunk, n // (args.folds + 8))
    max_fit = max(min_chunk, (n - win - 20) // (args.folds + 3))
    eval_chunk = min(desired, max_fit)
    k = 4 * eval_chunk
    print(f"dataset {n} bars, folds={args.folds}, eval_chunk={eval_chunk}, window_k={k}")

    results = []
    t0 = time.time()
    for j in range(args.folds):
        eval_end = n - j * eval_chunk
        eval_start = eval_end - eval_chunk
        train_end = eval_start
        train_start = max(0, eval_start - 3 * eval_chunk)
        if train_start < win + 20:
            break  # not enough bars for train window
        train_p = prices.iloc[train_start:train_end]
        train_f = feats.iloc[train_start:train_end]
        test_p = prices.iloc[eval_start:eval_end]
        test_f = feats.iloc[eval_start:eval_end]

        if args.checkpoint:
            model = challenger_model
        else:
            env = Monitor(GymV21CompatibilityV0(env=build_env(train_p, train_f)))
            model = PPO("MlpPolicy", env, verbose=0, device="cpu",
                        n_steps=2048, batch_size=256, learning_rate=3e-4,
                        gamma=0.99, ent_coef=0.01)
            model.learn(total_timesteps=args.timesteps)

        oos = simulate_oos(test_p, test_f, model)
        oos["fold"] = j + 1
        oos["train_bars"] = train_end - train_start
        oos["test_start"] = str(test_p.index[0])
        oos["test_end"] = str(test_p.index[-1])
        results.append(oos)
        print(f"fold {j+1}/{args.folds}: OOS sharpe={oos['ann_sharpe']:.3f} "
              f"ret={oos['net_return']:.4f} maxdd={oos['max_dd']:.3f} "
              f"train=[{train_start},{train_end}) test=[{eval_start},{eval_end}) "
              f"[{round(time.time()-t0,0)}s elapsed]", flush=True)

    if len(results) < 4:
        print(f"WARN: only {len(results)} folds evaluated (< 4 requested)")

    if not results:
        print("ERROR: no folds evaluated (dataset too short for any window)")
        sys.exit(2)

    sharpe_arr = np.array([r["ann_sharpe"] for r in results])
    mean_sharpe = float(sharpe_arr.mean())
    neg = int((sharpe_arr < 0).sum())
    ret_arr = np.array([r["net_return"] for r in results])
    summary = {
        "symbol": config.SYMBOL,
        "timesteps": args.timesteps,
        "bars_used": n,
        "folds_evaluated": len(results),
        "mean_oos_ann_sharpe": round(mean_sharpe, 4),
        "negative_sharpe_folds": neg,
        "folds": results,
        "verdict": "PASS" if mean_sharpe > 0 else "FAIL",
        "gated_checkpoint": os.path.basename(args.checkpoint) if args.checkpoint else None,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"wrote verdict -> {out_path}")
    print(json.dumps(summary, indent=2))
    print("VERDICT:", summary["verdict"])
    sys.exit(0 if mean_sharpe > 0 else 1)


if __name__ == "__main__":
    main()
