# Post 2 — The Gate (Aug 28)

**Your backtest means nothing without an out-of-sample gate.**

Everyone quotes Sharpe from in-sample training runs. The council's spec demanded a walk-forward OOS harness: 75/25 rolling windows, ≥4 folds, train on the past, evaluate strictly on the unseen 25%.

Here's what the gate did to my crypto lane:

| Fold | Annualized Sharpe | Return | MaxDD |
|------|-----------------|--------|-------|
| 1 | +0.41 | +0.07% | 1.91% |
| 2 | **−9.43** | −2.34% | 3.84% |
| 3 | +5.58 | +1.36% | 2.70% |
| 4 | +26.95 | +6.90% | 1.58% |
| **Mean** | **+5.88** | **+1.50%** | **2.51%** |

Mean Sharpe **5.88** looks great — but **1 of 4 folds is deeply negative**. That's not a bot, that's a coin flip with good advertising. Verdict: crypto lane **demoted to secondary**. High variance, not trustworthy as the primary entry.

The honest lesson: a single number (even a good one) is a trap. The distribution is the truth. RiskFirst's primary lane is options+equities with vol-targeting and hard guardrails — because a gate that can fail you is the only gate worth having.

Walk-forward harness: `cryptobot/eval_oos.py`, 300k timesteps / 25,766 bars, ETH/USD. Full fold record: `cryptobot/state/ETHUSD/eval_oos_full.json`.
