"""LLM risk referee — the advisory LLM at the decision center.

VOLTAIR's pitch claims an "LLM at the decision center." This module makes that
claim literally true: every proposal that passes the deterministic risk
arbiter is ALSO reviewed by a local LLM, and the LLM's verdict + reasoning are
written to the decision log as part of the auditable P&L narrative.

Design rules (important — keep them):
  * The deterministic risk arbiter is the ONLY enforcement layer. Position
    size, drawdown pause, cash cover, and the daily-loss circuit are hard
    gates in code. The LLM is advisory: its verdict is recorded for the audit
    trail but does not block a proposal unless enforcement is explicitly
    enabled (OLLAMA_REFEREE_ENFORCE=1) — and even then it can only VETO, never
    approve. This is deliberate: local small models hallucinate numeric
    checks, so the LLM must never be the sole authority over a real decision.
  * Fail-open: any timeout, outage, or unparseable response => "no opinion"
    (never blocks, never stalls a cycle). Every HTTP call has a hard timeout
    (default 30s — a cold model load on a busy box takes ~12s).
  * The referee must return strict JSON so the arbiter can parse it
    deterministically. Free text is treated as "no opinion".
  * Default model is a small model that fits alongside prod services; override
    via env:
        OLLAMA_URL   (default http://127.0.0.1:11434)
        OLLAMA_MODEL (default qwen2.5:1.5b)
    The referee never needs Alpaca keys and never touches a live account —
    it only reads numbers already in memory.
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error

# --------------------------------------------------------------------------- #
# Ollama client (stdlib only — no new dependency)
# --------------------------------------------------------------------------- #

DEFAULT_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b")
TIMEOUT_S = float(os.environ.get("OLLAMA_REFEREE_TIMEOUT", "30"))
ENFORCE = os.environ.get("OLLAMA_REFEREE_ENFORCE", "0") == "1"


def _ask_ollama(prompt: str, model: str, url: str, timeout: float) -> str | None:
    """POST /api/generate to local Ollama. Returns text or None on any error."""
    try:
        body = json.dumps(
            {"model": model, "prompt": prompt, "stream": False,
             "options": {"temperature": 0.0, "num_predict": 300}},
        ).encode()
        req = urllib.request.Request(
            url + "/api/generate", data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
            return payload.get("response")
    except (urllib.error.URLError, urllib.error.HTTPError,
            TimeoutError, OSError, json.JSONDecodeError, KeyError):
        return None


def _parse_verdict(text: str) -> tuple[bool, str] | None:
    """Extract (approve: bool, reason: str) from a model response.

    Accepts strict JSON like {"approve": false, "reason": "..."} — either a
    bare JSON object or one embedded in prose. Anything unparseable returns
    None (no opinion => pass).
    """
    if not text:
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        # Try to find the first {...} block.
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            obj = json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(obj, dict):
        return None
    appr = obj.get("approve")
    if not isinstance(appr, bool):
        return None
    reason = str(obj.get("reason", "")).strip()[:200]
    return appr, reason or ("no reason given" if not appr else "no reason given")


# --------------------------------------------------------------------------- #
# Referee
# --------------------------------------------------------------------------- #

class LLMReferee:
    """Advisory LLM reviewer. Records an opinion; vetoes only if enforce=True."""

    def __init__(self, model: str = DEFAULT_MODEL, url: str = DEFAULT_URL,
                 timeout: float = TIMEOUT_S, enforce: bool = ENFORCE):
        self.model = model
        self.url = url
        self.timeout = timeout
        self.enforce = enforce

    def review(self, proposal, account: dict, cash: float) -> tuple[bool, str]:
        """Return (approve: bool, reason: str).

        approve=False means the LLM has a veto opinion (only blocks when
        enforce=True). Any error/timeout/unparseable => (True, reason) so the
        referee never stalls a cycle and never blocks on its own failure.
        """
        if self.enforce is False:
            # Advisory-only mode: still get the opinion, but never let it
            # block. Used to populate the audit trail.
            pass

        context = {
            "strategy": proposal.strategy,
            "symbol": proposal.symbol,
            "underlying": proposal.underlying,
            "side": proposal.side,
            "qty": proposal.qty,
            "limit_price": proposal.price,
            "delta": round(proposal.delta, 3),
            "dte": proposal.dte,
            "iv_rank": round(proposal.iv_rank, 3),
            "notional": round(proposal.notional, 2),
            "account_equity": round(account.get("equity", 0.0), 2),
            "account_cash": round(cash, 2),
        }
        prompt = (
            "You are a risk-review assistant for a paper-options trading agent. "
            "A deterministic risk arbiter has already accepted this proposal "
            "against hard limits (position size, drawdown, cash cover, daily "
            "loss). Your task: give a QUALITATIVE review for the audit log — "
            "structure sanity, direction of risk, obvious mismatches (e.g. a "
            "covered call on shares not held). You do NOT need to re-verify "
            "numbers; the hard gates already did. Respond with STRICT JSON "
            "only: {\"approve\": true|false, \"reason\": \"short note\"}.\n"
            f"Proposal: {json.dumps(context)}\n"
            "JSON:"
        )
        text = _ask_ollama(prompt, self.model, self.url, self.timeout)
        if text is None:
            return True, "referee unreachable (no opinion)"
        parsed = _parse_verdict(text)
        if parsed is None:
            return True, "referee no structured opinion"
        approve, reason = parsed
        return approve, reason
