"""End-to-end smoke test: data -> features -> env -> random rollout -> obs parity."""
import numpy as np

import config
from bot import data
from bot.env import build_env


def main():
    prices, feats = data.load_dataset()
    print(f"bars={len(prices)} features={feats.shape[1]} "
          f"last_close={prices['close'].iloc[-1]:.2f}")
    assert len(feats) > 500, "not enough data"

    env = build_env(prices, feats)
    obs = env.reset()
    print("env obs shape:", obs.shape)

    nw0 = None
    for i in range(200):
        action = env.action_space.sample()
        obs, reward, done, info = env.step(action)
        if nw0 is None:
            nw0 = info["net_worth"]
        if done:
            break
    print(f"rollout ok: steps={i+1} nw {nw0:.0f} -> {info['net_worth']:.0f}")

    live_obs = feats.tail(config.WINDOW_SIZE).to_numpy(dtype=np.float32)
    assert live_obs.shape == obs.shape, f"obs mismatch: live {live_obs.shape} vs env {obs.shape}"
    print("live/train observation parity OK:", live_obs.shape)
    print("SMOKE TEST PASSED")


if __name__ == "__main__":
    main()
