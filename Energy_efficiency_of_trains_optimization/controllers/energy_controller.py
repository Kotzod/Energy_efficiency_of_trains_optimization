"""Energy-aware driving decisions for the existing railway safety model."""

from dataclasses import dataclass
from typing import Any

ACTIONS = ("ACCELERATE", "CRUISE", "COAST", "BRAKE", "HOLD")


@dataclass(frozen=True)
class ControllerDecision:
    action: str
    reason: str
    estimated_saving_kwh: float = 0.0


def _edge(train: Any):
    if train.next_node is None:
        return None
    return train._get_edge_between(train.current_node, train.next_node)


def _effective_limits(train: Any) -> tuple[float, float, float]:
    speed_factor, accel_factor, brake_factor = train._get_weather_factors()
    edge = _edge(train)
    speed_limit = train.base_max_speed_ms
    if edge is not None:
        speed_limit = min(speed_limit, edge.speed_limit_kmh / 3.6)
    speed_limit *= speed_factor * getattr(train, "scenario_speed_factor", 1.0)
    return speed_limit, train.base_acceleration_ms2 * accel_factor, max(
        train.base_deceleration_ms2 * brake_factor, 0.01
    )


def _next_stop_distance(train: Any) -> float:
    """Distance to the next station, in metres, across the current route edge."""
    if train.next_node is None:
        return float("inf")
    return abs(train._get_node_km(train.next_node) - train.abs_position_km) * 1000


def _opposing_conflict(train: Any) -> Any:
    """Find an opposing train in the uninterrupted single-track lookahead."""
    edge_index = train.edge_index
    if train.next_node is None:
        return None
    end_index = len(train.route) - 1
    for index in range(edge_index, len(train.route) - 1):
        edge = train._get_edge_between(train.route[index], train.route[index + 1])
        if edge is None or edge.tracks != 1:
            end_index = index
            break
        if train.model.graph.nodes[train.route[index + 1]].get("passing_loop", False):
            end_index = index + 1
            break
    section = set(train.route[edge_index : end_index + 1])
    for other in train.model.agents:
        if other is train or other.state.value == "terminated":
            continue
        if other.direction == train.direction:
            continue
        if other.current_node in section or other.next_node in section:
            return other
    return None


def _loses_equal_priority_tiebreak(train: Any, conflict: Any) -> bool:
    """
    Deterministic tiebreak for two equal-priority (same-type) trains facing
    each other across a single-track section. Whoever has waited longer
    goes; on an exact wait-time tie, the lower unique_id goes. Both trains
    read the same two facts about each other, so their independent decide()
    calls always resolve to complementary outcomes -- exactly one holds.
    """
    train_key = (-train.wait_time, train.unique_id)
    conflict_key = (-conflict.wait_time, conflict.unique_id)
    return train_key > conflict_key


class RuleBasedController:
    """Baseline predictive controller; safety remains in TrainAgent."""

    def decide(self, train: Any) -> ControllerDecision:
        if train._at_station:
            conflict = _opposing_conflict(train)
            if conflict is not None:
                # FIX: the old condition was `priority < conflict.priority or
                # priority == conflict.priority`, i.e. `priority <= conflict.priority`.
                # For two SAME-TYPE trains (equal priority) that is true on both
                # sides every tick, so both held forever with no way to break the
                # tie. Strictly-lower priority still always holds; equal priority
                # now resolves via wait time / unique_id instead of holding
                # unconditionally.
                if train.priority < conflict.priority:
                    return ControllerDecision(
                        "HOLD",
                        f"Opposing train {conflict.unique_id} (higher priority) detected in the next single-track section; holding before departure avoids a later brake cycle.",
                    )
                if train.priority == conflict.priority and _loses_equal_priority_tiebreak(train, conflict):
                    return ControllerDecision(
                        "HOLD",
                        f"Opposing train {conflict.unique_id} (equal priority, waited longer) takes precedence; holding before departure avoids a later brake cycle.",
                    )
                # Otherwise this train has strictly higher priority, or wins the
                # equal-priority tiebreak -- fall through and depart normally.

        speed_limit, acceleration, braking = _effective_limits(train)
        speed = train.current_speed_ms
        distance = _next_stop_distance(train)
        braking_distance = speed**2 / (2 * braking)
        if speed > 0 and distance <= braking_distance + train.safety_margin_m:
            return ControllerDecision(
                "BRAKE",
                f"Station or safe stopping point is {distance:.0f} m ahead; braking distance is {braking_distance:.0f} m.",
            )
        if speed < speed_limit - 0.5:
            return ControllerDecision(
                "ACCELERATE",
                f"Below the current safe speed limit ({speed_limit * 3.6:.0f} km/h).",
            )
        return ControllerDecision("CRUISE", "At the current safe speed limit.")


class MPCController(RuleBasedController):
    """Lightweight rolling-horizon optimizer over the five driving actions."""

    def decide(self, train: Any) -> ControllerDecision:
        baseline = super().decide(train)
        if baseline.action in ("HOLD", "BRAKE"):
            return baseline

        # Coasting is only meaningful after a train has departed and has
        # kinetic energy. At a station, the train must accelerate first.
        if train._at_station or train.current_speed_ms <= 0.0:
            return ControllerDecision(
                "ACCELERATE",
                "Train is stationary; depart through the normal safety checks before coasting.",
            )

        speed_limit, acceleration, braking = _effective_limits(train)
        speed = train.current_speed_ms
        distance = _next_stop_distance(train)
        horizon_s = train.model.time_step * 60 * 4
        projected_speed = min(speed + acceleration * horizon_s, speed_limit)
        projected_distance = (speed + projected_speed) * horizon_s / 2
        stopping_after_horizon = projected_speed**2 / (2 * braking)

        if distance <= projected_distance + stopping_after_horizon + train.safety_margin_m:
            return ControllerDecision(
                "COAST",
                f"Rolling horizon predicts a stop {distance:.0f} m ahead; coasting avoids unnecessary traction before braking.",
                estimated_saving_kwh=max(0.0, projected_speed - speed) * 0.02,
            )
        if speed >= speed_limit - 0.5:
            return ControllerDecision("COAST", "Speed target is reached; coasting avoids excess traction.")
        return ControllerDecision("ACCELERATE", "Horizon predicts insufficient speed to reach the next target without delay.")