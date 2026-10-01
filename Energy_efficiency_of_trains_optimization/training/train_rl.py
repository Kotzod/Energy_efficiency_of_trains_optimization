"""Train a PPO policy offline. Requires requirements-rl.txt."""

from pathlib import Path

from training.railway_env import RailwayEnergyEnv


def main():
    try:
        from stable_baselines3 import PPO
    except ImportError as exc:
        raise SystemExit("Install requirements-rl.txt before training PPO") from exc

    checkpoint = Path("training/checkpoints/railway_ppo")
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    env = RailwayEnergyEnv()
    model = PPO("MlpPolicy", env, verbose=1, seed=67)
    model.learn(total_timesteps=10_000)
    model.save(str(checkpoint))
    print(f"Saved PPO checkpoint to {checkpoint}")


if __name__ == "__main__":
    main()
