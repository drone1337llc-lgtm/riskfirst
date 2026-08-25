"""Live test of the Ollama macro-regime call with real market data."""
import logging
logging.basicConfig(level=logging.INFO)

from bot import data, macro

_, feats = data.load_dataset()
print("snapshot:", macro.build_snapshot(feats) + macro.get_fear_greed())
print("ollama url:", macro.OLLAMA_URL)
out = macro.get_macro_regime(feats)
print("RESULT:", out)
assert out["regime"] in ("bull", "bear", "volatile", "neutral")
assert 0.0 <= out["max_allocation"] <= 1.0
print("MACRO TEST PASSED" if out.get("reason") != "llm unavailable" else "FELL BACK TO SAFE DEFAULT")
