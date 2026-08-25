# Post 2 — The Gate (Aug 28)

** Your backtest means nothing without an out-of-sample gate.**

Everyone quotes Sharpe from in-sample training runs. The council's spec demanded a walk-forward OOS harness: 75/25 rolling windows, ≥4 folds, train on the past, evaluate strictly on the unseen 25%.

Here's what the gate did to my crypto lane:

| Fold | Annualized Sharpe | Return | MaxDD |
|------|-----------------|--------|-------|
| 1 | +0.41 | — | — |
| 2 | **−9.43** | — | — |
| 3 | +5.58 | — | — |
| 4 | +26.95 | — | — |
| **Mean** | **+5.88** | — | — |

Mean Sharpe **5.88** looks great — but **1 of 4 folds is deeply negative**. That's not a bot, that's a coin flip with good advertising. Verdict: crypto lane **demoted to secondary**. High variance, not trustworthy as the primary entry.

The honest lesson: a single number (even a good one) is a trap. The distribution is the truth. RiskFirst's primary lane is options+equities with vol-targeting and hard guardrails — because a gate that can fail you is the only gate worth having.

Walk-forward harness: eval_oos.py, 300k timesteps / 25,766 bars, ETH/USD.
