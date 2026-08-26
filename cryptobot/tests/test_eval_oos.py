"""Eval reproducibility tests — eval_oos.py seeded determinism.

The OOS verdict is the crypto lane's hard gate, so the reported Sharpe must be
reproducible: the same seed must produce byte-identical fold results, and the
verdict must record the seed used. These tests pin that contract with no
network (load_dataset monkeypatched) and tiny budgets.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # cryptobot/
import config
import eval_oos


FEAT_COLS = [
    "ret_1", "ret_4", "ret_24", "rsi", "macd", "vol_z",
    "hl_range", "volat_24", "btc_ret_1", "btc_ret_24", "btc_rsi",
]


def _fake_dataset(n=4000, seed=0):
    rng = np.random.default_rng(seed)
    rets = rng.normal(0, 0.001, n)
    close = 2000 * np.exp(np.cumsum(rets))
    prices = pd.DataFrame({"close": close}, index=pd.date_range("2026-01-01", periods=n, freq="min"))
    feats = pd.DataFrame(rng.normal(0, 1, (n, len(FEAT_COLS))), columns=FEAT_COLS, index=prices.index)
    return prices, feats


@pytest.fixture
def fake_data(monkeypatch):
    monkeypatch.setattr("bot.data.load_dataset", lambda: _fake_dataset())


def _run_eval(monkeypatch, out_path, seed, timesteps=300):
    monkeypatch.setattr(
        sys, "argv",
        ["eval_oos.py", "--seed", str(seed), "--timesteps", str(timesteps),
         "--out", str(out_path)])
    with pytest.raises(SystemExit) as e:
        eval_oos.main()
    assert e.value.code in (0, 1)  # PASS/FAIL both valid; determinism is what we pin
    with open(out_path) as f:
        return json.load(f)


def test_seeded_runs_are_bit_identical(tmp_path, fake_data, monkeypatch):
    """Same seed -> identical fold Sharpe array + recorded seed."""
    a = _run_eval(monkeypatch, str(tmp_path / "a.json"), seed=42)
    b = _run_eval(monkeypatch, str(tmp_path / "b.json"), seed=42)
    assert a["folds_evaluated"] == b["folds_evaluated"] >= 2
    sa = [r["ann_sharpe"] for r in a["folds"]]
    sb = [r["ann_sharpe"] for r in b["folds"]]
    assert sa == sb
    assert a["mean_oos_ann_sharpe"] == b["mean_oos_ann_sharpe"]
    assert a["seed"] == 42
    assert a["fold_seeds"] == [42 + j for j in range(a["folds_evaluated"])]


def test_different_seed_changes_result(tmp_path, fake_data, monkeypatch):
    """The seed actually bites: different seed -> (likely) different training run."""
    a = _run_eval(monkeypatch, str(tmp_path / "a.json"), seed=1)
    b = _run_eval(monkeypatch, str(tmp_path / "b.json"), seed=2)
    sa = [f["ann_sharpe"] for f in a["folds"]]
    sb = [f["ann_sharpe"] for f in b["folds"]]
    # Stochastic RL: different seeds should not collide on every fold.
    assert any(x != y for x, y in zip(sa, sb))
