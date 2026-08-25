import importlib
for m in ["tensortrade", "gym", "stable_baselines3", "alpaca", "torch", "pandas", "numpy", "requests", "dotenv"]:
    try:
        mod = importlib.import_module(m)
        print(f"OK  {m:20s} {getattr(mod, '__version__', '?')}")
    except Exception as e:
        print(f"FAIL {m:20s} {type(e).__name__}: {e}")
