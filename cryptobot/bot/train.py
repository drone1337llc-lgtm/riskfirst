"""Train PPO on the TensorTrade env (run locally on CPU or on RunPod GPU)."""
import argparse
import os

from shimmy import GymV21CompatibilityV0
from stable_baselines3 import PPO
from stable_baselines3.common.monitor import Monitor

import config
from bot import data, promote
from bot.env import build_env


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--timesteps", type=int, default=300_000)
    p.add_argument("--out", default=config.CHALLENGER_PATH,
                   help="output path (default challenger; champion path is refused)")
    p.add_argument("--device", default="auto")
    args = p.parse_args()
    promote.check_not_champion(args.out)

    prices, feats = data.load_dataset()
    print(f"dataset: {len(feats)} bars, {feats.shape[1]} features")

    env = Monitor(GymV21CompatibilityV0(env=build_env(prices, feats)))
    model = PPO("MlpPolicy", env, verbose=1, device=args.device,
                n_steps=2048, batch_size=256, learning_rate=3e-4,
                gamma=0.99, ent_coef=0.01)
    model.learn(total_timesteps=args.timesteps)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    model.save(args.out)
    print(f"saved checkpoint -> {args.out}")


if __name__ == "__main__":
    main()
