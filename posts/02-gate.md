# Post 2 — The Gate (Aug 28)

**Your backtest means nothing without an out-of-sample gate.**

Everyone quotes Sharpe from in-sample training runs. The council's spec demanded a walk-forward OOS harness: 75/25 rolling windows, ≥4 folds, train on the past, evaluate strictly on the unseen 25%.

Here's what the gate did to my crypto lane:

| Fold | Annualized Sharpe | Return | MaxDD |
|------|-----------------|--------|-------|
| 1 | **−2.43** | −0.35% | 1.44% |
| 2 | +14.57 | +3.56% | 2.01% |
| 3 | **−2.86** | −0.81% | 3.98% |
| 4 | +0.13 | +0.04% | 5.16% |
| **Mean** | **+2.35** | **+0.61%** | **3.15%** |

Mean Sharpe **2.35** with **2 of 4 folds negative** — under a fixed seed (42), so any judge can reproduce it. That's high variance with a thin edge, not a trustable primary. Verdict: crypto lane **demoted to secondary**. High variance, not trustworthy as the primary entry.

The honest lesson: a single number (even a good one) is a trap — which is why the canonical verdict is now seeded and reproducible. The distribution is the truth. RiskFirst's primary lane is options+equities with vol-targeting and hard guardrails — because a gate that can fail you is the only gate worth having.

Walk-forward harness: `cryptobot/eval_oos.py`, 300k timesteps / 25,985 bars, ETH/USD. Full fold record: `evals/ETHUSD_eval_oos_full.json`.
