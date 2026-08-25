"""LLM macro-regime classification via local Ollama (structured JSON)."""
import json
import logging
import subprocess

import requests

import config

log = logging.getLogger("macro")


def _resolve_ollama_url() -> str:
    """Windows-host Ollama from WSL: try configured URL, fall back to WSL gateway."""
    candidates = [config.OLLAMA_URL]
    try:
        gw = subprocess.check_output(
            "ip route show default | awk '{print $3}'", shell=True, text=True).strip()
        if gw:
            candidates.append(f"http://{gw}:11434")
    except Exception:
        pass
    for url in candidates:
        try:
            requests.get(f"{url}/api/version", timeout=3).raise_for_status()
            return url
        except Exception:
            continue
    return config.OLLAMA_URL


OLLAMA_URL = _resolve_ollama_url()

SAFE_DEFAULT = {"regime": "volatile", "max_allocation": 0.25, "reason": "llm unavailable"}

_SCHEMA = {
    "type": "object",
    "properties": {
        "regime": {"type": "string", "enum": ["bull", "bear", "volatile", "neutral"]},
        "max_allocation": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "reason": {"type": "string"},
    },
    "required": ["regime", "max_allocation"],
}

PROMPT = """You are a crypto macro risk officer. Given the market snapshot below,
classify the regime and set a maximum portfolio allocation cap (0.0-1.0) for an
automated trading agent. Be conservative: high volatility or extreme greed/fear
should lower the cap.

Snapshot:
{snapshot}

Respond only with JSON: {{"regime": ..., "max_allocation": ..., "reason": ...}}"""


def build_snapshot(feats) -> str:
    """Compact plain-text market snapshot from the latest feature row."""
    r = feats.iloc[-1]
    return (
        f"{config.SYMBOL} 24-bar return: {r['ret_24']:+.2%}, RSI: {r['rsi']*100:.0f}, "
        f"24-bar volatility: {r['volat_24']:.4f}, volume z-score: {r['vol_z']:+.1f}. "
        f"BTC 24-bar return: {r['btc_ret_24']:+.2%}, BTC RSI: {r['btc_rsi']*100:.0f}."
    )


def get_fear_greed() -> str:
    try:
        j = requests.get("https://api.alternative.me/fng/?limit=1", timeout=10).json()
        d = j["data"][0]
        return f" Fear & Greed Index: {d['value']} ({d['value_classification']})."
    except Exception:
        return ""


def get_macro_regime(feats) -> dict:
    """Query Ollama; on any failure return the conservative default."""
    snapshot = build_snapshot(feats) + get_fear_greed()
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": config.OLLAMA_MODEL,
                "prompt": PROMPT.format(snapshot=snapshot),
                "format": _SCHEMA,
                "stream": False,
                "options": {"temperature": 0.2},
            },
            timeout=180,
        )
        resp.raise_for_status()
        out = json.loads(resp.json()["response"])
        out["max_allocation"] = max(0.0, min(1.0, float(out["max_allocation"])))
        log.info("macro regime=%s cap=%.2f (%s)", out["regime"],
                 out["max_allocation"], out.get("reason", ""))
        return out
    except Exception as e:
        log.warning("LLM macro failed (%s); using safe default", e)
        return dict(SAFE_DEFAULT)
