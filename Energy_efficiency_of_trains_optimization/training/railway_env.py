"""Gymnasium environment wrapping the existing RailwayModel for PPO training."""

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError as exc:  # pragma: no cover - optional training dependency
    raise RuntimeError("Install requirements-rl.txt to use the PPO environment") from exc

import numpy as np

from controllers.energy_controller import ACTIONS
from infrastructure.railway_graph import RailwayModel


class RailwayEnergyEnv(gym.Env):
    """Single-control-train environment; infrastructure safety stays in the model."""

    metadata = {"render_modes": []}

    def __init__(self, seed: int = 67, horizon: int = 240):
        self.seed_value = seed
        self.horizon = horizon
        self.action_space = spaces.Discrete(len(ACTIONS))
        self.observation_space = spaces.Box(
            low=np.array([0.0, -1e4, -5.0, 0.0, 0.0], dtype=np.float32),
            high=np.array([100.0, 1e4, 5.0, 1e5, 2.0], dtype=np.float32),
        )
        self.model = None
        self.train = None
        self.ticks = 0

    def _observation(self):
        if self.train is None:
            return np.zeros(5, dtype=np.float32)
        return np.array([
            self.train.current_speed_ms,
            self.train.abs_position_km,
            self.train.current_acceleration_ms2,
            self.train.total_delay_ticks,
            self.train._get_weather_factors()[0],
        ], dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        actual_seed = self.seed_value if seed is None else seed
        self.model = RailwayModel(seed=actual_seed)
        self.model.set_controller_mode("rule_based")
        self.train = next(iter(self.model.agents), None)
        self.ticks = 0
        return self._observation(), {}

    def step(self, action):
        if self.train is None:
            return self._observation(), 0.0, True, False, {}
        before = self.train.energy_consumed_kwh - self.train.energy_regenerated_kwh
        before_delay = self.train.total_delay_ticks
        self.train.external_action = ACTIONS[int(action)]
        self.model.step()
        self.train.external_action = None
        self.ticks += 1
        energy_delta = (
            self.train.energy_consumed_kwh
            - self.train.energy_regenerated_kwh
            - before
        )
        delay_delta = self.train.total_delay_ticks - before_delay
        reward = -energy_delta - (0.05 * delay_delta)
        terminated = self.train.state.value == "terminated"
        truncated = self.ticks >= self.horizon
        return self._observation(), float(reward), terminated, truncated, {
            "energy_kwh": energy_delta,
            "delay_ticks": delay_delta,
        }
