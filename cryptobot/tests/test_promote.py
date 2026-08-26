"""Champion/challenger promote contract — enforce the 'promote only on OOS win' rule.

README 'Risk rails (both lanes)' claims: a challenger only replaces the live
lane on an OOS win, never on training loss. These tests pin that contract:
  - training may never write the live champion path;
  - promote refuses unless the challenger's walk-forward OOS verdict is
    strictly positive AND strictly beats the recorded incumbent;
  - a winning challenger atomically replaces the champion + records the metric.
No network, no model loads (zip validity is all promote needs to copy).
"""
from __future__ import annotations

import json
import os
import pathlib
import zipfile

import pytest

import config
from bot import promote


@pytest.fixture
def champ_env(tmp_path, monkeypatch):
    """Point config at a tmp state/champion pair; return builder helpers."""
    state = tmp_path / "state"
    state.mkdir()
    ckpt = tmp_path / "checkpoints" / "ppo_ETHUSD.zip"
    ckpt.parent.mkdir()

    monkeypatch.setattr(config, "STATE_DIR", str(state))
    monkeypatch.setattr(config, "CHECKPOINT_PATH", str(ckpt))
    monkeypatch.setattr(config, "CHALLENGER_PATH", str(ckpt.with_name("ppo_ETHUSD_challenger.zip")))

    def _make_zip(path) -> str:
        p = tmp_path / path
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("data", b"x")
        return str(p)

    def _verdict(mean, name="eval_oos_challenger.json"):
        """Write a challenger verdict into the fixture state dir; return state dir."""
        (state / name).write_text(json.dumps(
            {"mean_oos_ann_sharpe": mean, "verdict": "PASS" if mean > 0 else "FAIL"}))
        return str(state)

    def _record(mean):
        (state / promote.PROMOTE_FILE).write_text(json.dumps(
            {"champion": str(ckpt), "mean_oos_ann_sharpe": mean}))

    _make_zip.champ = str(ckpt)
    _make_zip.challenger = str(ckpt.with_name("ppo_ETHUSD_challenger.zip"))
    _make_zip.state = str(state)
    _make_zip.verdict = _verdict
    _make_zip.record = _record
    return _make_zip


# --- train may never write the champion ---------------------------------------


def test_challenger_and_champion_paths_distinct():
    assert config.CHALLENGER_PATH != config.CHECKPOINT_PATH
    assert "_challenger.zip" in config.CHALLENGER_PATH


def test_check_not_champion_refuses_champion_path(champ_env):
    with pytest.raises(ValueError):
        promote.check_not_champion(champ_env.champ)


def test_check_not_champion_allows_challenger_path(champ_env):
    promote.check_not_champion(champ_env.challenger)  # must not raise


# --- promote fail-closed rules --------------------------------------------------


def test_promote_refuses_missing_challenger(champ_env):
    res = promote.promote_checkpoint("/nope/missing.zip")
    assert not res["ok"]
    assert "not found" in res["reason"]


def test_promote_refuses_non_zip_challenger(champ_env, tmp_path):
    junk = tmp_path / "junk.zip"
    junk.write_text("not a zip")
    res = promote.promote_checkpoint(str(junk))
    assert not res["ok"]
    assert "not a zip" in res["reason"]


def test_promote_refuses_without_verdict(champ_env):
    ch = champ_env("challenger.zip")
    res = promote.promote_checkpoint(ch)
    assert not res["ok"]
    assert "no challenger verdict" in res["reason"]


def test_promote_refuses_negative_verdict(champ_env):
    ch = champ_env("challenger.zip")
    champ_env.verdict(-1.2)
    res = promote.promote_checkpoint(ch)
    assert not res["ok"]
    assert "not positive net" in res["reason"]


def test_promote_refuses_when_not_beating_incumbent(champ_env):
    ch = champ_env("challenger.zip")
    champ_env.verdict(4.0)
    champ_env.record(5.0)
    res = promote.promote_checkpoint(ch)
    assert not res["ok"]
    assert "does not beat incumbent" in res["reason"]


def test_promote_succeeds_on_winning_verdict(champ_env):
    ch = champ_env("challenger.zip")
    champ_env.verdict(6.5)
    res = promote.promote_checkpoint(ch)
    assert res["ok"]
    assert res["mean_sharpe"] == 6.5
    assert os.path.isfile(champ_env.champ)  # champion replaced
    rec = json.loads(open(os.path.join(champ_env.state, promote.PROMOTE_FILE)).read())
    assert rec["mean_oos_ann_sharpe"] == 6.5


def test_promote_succeeds_beating_incumbent(champ_env):
    ch = champ_env("challenger.zip")
    champ_env.verdict(7.1)
    champ_env.record(5.0)
    res = promote.promote_checkpoint(ch)
    assert res["ok"]
    rec = json.loads(open(os.path.join(champ_env.state, promote.PROMOTE_FILE)).read())
    assert rec["mean_oos_ann_sharpe"] == 7.1


def test_promote_force_bypasses_verdict(champ_env):
    ch = champ_env("challenger.zip")  # no verdict file at all
    res = promote.promote_checkpoint(ch, force=True)
    assert res["ok"]
    assert res["reason"] == "promoted (force)"
