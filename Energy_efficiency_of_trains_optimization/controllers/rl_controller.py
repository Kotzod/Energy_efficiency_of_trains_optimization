"""Optional PPO inference controller.

A checkpoint must be trained offline before this controller can be selected.
"""

from pathlib import Path

from controllers.energy_controller import ACTIONS, ControllerDecision, RuleBasedController


class RLController(RuleBasedController):
    def __init__(self, model_path: str | Path):
        try:
            from stable_baselines3 import PPO
        except ImportError as exc:
            raise RuntimeError(
                "AI controller requires stable-baselines3; install requirements-rl.txt"
            ) from exc
        path = Path(model_path)
        if not path.exists():
            raise FileNotFoundError(f"No trained PPO checkpoint at {path}")
        self.model = PPO.load(str(path))

    def decide(self, train):
        observation = [
            train.current_speed_ms,
            train.abs_position_km,
            float(train.current_acceleration_ms2),
            float(train.total_delay_ticks),
            float(train._get_weather_factors()[0]),
        ]
        action_index, _ = self.model.predict(observation, deterministic=True)
        action = ACTIONS[int(action_index)]
        safe_fallback = super().decide(train)
        if action == "HOLD" and not train._at_station:
            action = safe_fallback.action
        return ControllerDecision(
            action,
            f"PPO checkpoint selected {action}; safety fallback remains {safe_fallback.action} when required.",
        )
