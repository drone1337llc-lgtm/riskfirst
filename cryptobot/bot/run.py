"""24/7 autonomous loop: data -> LLM macro -> RL policy -> guarded execution."""
import json
import logging
import os
import time
from datetime import datetime, timezone

import numpy as np
from stable_baselines3 import PPO

import config
from bot import data, macro

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(os.path.join(config.STATE_DIR, "bot.log"))],
)
log = logging.getLogger("run")


def latest_observation(feats) -> np.ndarray:
    """Stack the last WINDOW_SIZE feature rows to match the training observer."""
    window = feats.tail(config.WINDOW_SIZE).to_numpy(dtype=np.float32)
    return window


def write_status(payload: dict):
    payload["ts"] = datetime.now(timezone.utc).isoformat()
    with open(os.path.join(config.STATE_DIR, "status.json"), "w") as f:
        json.dump(payload, f, indent=2, default=str)


def main():
    from bot import execute  # imported here so data/train work without keys

    model = PPO.load(config.CHECKPOINT_PATH, device="cpu")
    log.info("policy loaded from %s", config.CHECKPOINT_PATH)

    macro_state = dict(macro.SAFE_DEFAULT)
    last_macro = 0.0
    backoff = 5

    while True:
        try:
            prices, feats = data.load_dataset()

            if time.time() - last_macro > config.MACRO_INTERVAL_S:
                macro_state = macro.get_macro_regime(feats)
                last_macro = time.time()

            obs = latest_observation(feats)
            action, _ = model.predict(obs, deterministic=True)
            target = config.TARGET_ALLOCATIONS[int(action)]
            log.info("policy action=%d target_alloc=%.2f regime=%s cap=%.2f",
                     int(action), target, macro_state["regime"],
                     macro_state["max_allocation"])

            result = execute.rebalance_to(target, macro_state["max_allocation"])
            write_status({"macro": macro_state, "target": target, "result": result,
                          "price": float(prices['close'].iloc[-1])})

            backoff = 5
            time.sleep(config.DECISION_INTERVAL_S)
        except KeyboardInterrupt:
            log.info("stopped by user")
            break
        except Exception:
            log.exception("loop error; retrying in %ss", backoff)
            time.sleep(backoff)
            backoff = min(backoff * 2, 600)


if __name__ == "__main__":
    main()
