"""Zero-commission rail: orders must FILL, never silently cancel.

TensorTrade's stock simulator guards against sub-precision commissions:
if 0 < commission < 10**-precision it CANCELS the order outright. A naive
commission=0 fix must therefore be proven to actually trade — otherwise the
"honest" config just hugs cash. This pins that contract empirically at the
real env: at COMMISSION=0 every placed order fills, zero cancels.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import config
from bot.env import build_env


FEAT_COLS = [
    "ret_1", "ret_4", "ret_24", "rsi", "macd", "vol_z",
    "hl_range", "volat_24", "btc_ret_1", "btc_ret_24", "btc_rsi",
]


def _fake_dataset(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0, 0.001, n)
    close = 2000 * np.exp(np.cumsum(rets))
    prices = pd.DataFrame({"close": close}, index=pd.date_range("2026-01-01", periods=n, freq="min"))
    feats = pd.DataFrame(rng.normal(0, 1, (n, len(FEAT_COLS))), columns=FEAT_COLS, index=prices.index)
    return prices, feats


def test_zero_commission_fills_every_order(monkeypatch):
    """COMMISSION=0 must trade: every placed order fills, zero cancels."""
    monkeypatch.setattr(config, "COMMISSION", 0.0)
    prices, feats = _fake_dataset()
    env = build_env(prices, feats, window_size=config.WINDOW_SIZE)
    portfolio = env.action_scheme.portfolio

    obs = env.reset()
    done = False
    steps = 0
    while not done and steps < 150:
        env.step(env.action_space.sample())
        steps += 1

    locks = fills = 0
    for t in portfolio.ledger.transactions:
        if "LOCK FOR ORDER" in t.memo:
            locks += 1
        elif "FILL ORDER" in t.memo:
            fills += 1

    assert locks > 0, "env placed no orders — cannot verify the zero-commission rail"
    assert fills == locks, f"{fills} fills vs {locks} orders — silent cancels at COMMISSION=0"
