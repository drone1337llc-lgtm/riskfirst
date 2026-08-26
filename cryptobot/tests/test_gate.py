"""Hard-gate enforcement tests — bot.gate fail-closed behavior.

The crypto lane must refuse startup unless the walk-forward OOS verdict is
present, readable, and positive net. These tests pin that contract with no
network and no model loads.
"""
from __future__ import annotations

import json

import pytest

from bot import gate


@pytest.fixture
def verdict_dir(tmp_path):
    """Write a verdict payload into tmp_path; return the dir path."""
    def _write(name, payload):
        p = tmp_path / name
        p.write_text(json.dumps(payload))
        return str(p)

    _write.path = tmp_path
    return _write


def _payload(mean, verdict="PASS", **kw):
    d = {"mean_oos_ann_sharpe": mean, "verdict": verdict, "folds": 4}
    d.update(kw)
    return d


# ---------------------------------------------------------------------------
# pass cases
# ---------------------------------------------------------------------------

def test_pass_on_positive_sharpe(verdict_dir):
    verdict_dir("eval_oos_full.json", _payload(5.8797))
    r = gate.check_oos_gate(str(verdict_dir.path))
    assert r["ok"] is True
    assert r["mean_sharpe"] == 5.8797
    assert r["reason"] is None


def test_pass_prefers_full_file(verdict_dir):
    verdict_dir("eval_oos.json", _payload(1.0))
    verdict_dir("eval_oos_full.json", _payload(5.88))
    r = gate.check_oos_gate(str(verdict_dir.path))
    assert r["ok"] is True
    assert r["mean_sharpe"] == 5.88
    assert r["file"].endswith("eval_oos_full.json")


def test_pass_accepts_small_positive(verdict_dir):
    verdict_dir("eval_oos_full.json", _payload(0.0001))
    r = gate.check_oos_gate(str(verdict_dir.path))
    assert r["ok"] is True


# ---------------------------------------------------------------------------
# fail-closed cases
# ---------------------------------------------------------------------------

def test_fail_on_negative_sharpe(verdict_dir):
    verdict_dir("eval_oos_full.json", _payload(-3.4, verdict="FAIL"))
    r = gate.check_oos_gate(str(verdict_dir.path))
    assert r["ok"] is False
    assert "not positive" in r["reason"]


def test_fail_on_hand_edited_pass_string(verdict_dir):
    # Verdict string lies; math must win.
    verdict_dir("eval_oos_full.json", _payload(-1.0, verdict="PASS"))
    r = gate.check_oos_gate(str(verdict_dir.path))
    assert r["ok"] is False


def test_fail_on_zero_sharpe(verdict_dir):
    verdict_dir("eval_oos_full.json", _payload(0.0, verdict="PASS"))
    r = gate.check_oos_gate(str(verdict_dir.path))
    assert r["ok"] is False


def test_fail_on_missing_file(tmp_path):
    r = gate.check_oos_gate(str(tmp_path))
    assert r["ok"] is False
    assert "no OOS verdict file" in r["reason"]


def test_fail_on_unreadable_file(verdict_dir):
    (verdict_dir.path / "eval_oos_full.json").write_text("{not json")
    r = gate.check_oos_gate(str(verdict_dir.path))
    assert r["ok"] is False
    assert "unreadable" in r["reason"]


def test_fail_on_missing_sharpe_field(verdict_dir):
    verdict_dir("eval_oos_full.json", {"verdict": "PASS", "folds": []})
    r = gate.check_oos_gate(str(verdict_dir.path))
    assert r["ok"] is False
    assert "mean_oos_ann_sharpe" in r["reason"]


# ---------------------------------------------------------------------------
# integration: run.py refuses startup when the gate fails
# ---------------------------------------------------------------------------

def test_run_main_exits_3_when_gate_fails(monkeypatch, tmp_path, caplog):
    """The lane entrypoint must fail closed at startup, before any trading."""
    import bot.run as run
    import config

    (tmp_path / "eval_oos_full.json").write_text(
        json.dumps(_payload(-1.5, verdict="FAIL")))

    # check_oos_gate reads config.STATE_DIR at call time — redirect it to the
    # tmp dir so the real enforcement path is exercised with a FAIL verdict.
    monkeypatch.setattr(config, "STATE_DIR", str(tmp_path))

    with pytest.raises(SystemExit) as e:
        run.main()
    assert e.value.code == 3
    assert any("FAILED CLOSED" in r.message for r in caplog.records)
