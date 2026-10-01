import math
import json
from pathlib import Path
from mesa import Agent
from enum import Enum
import logging

from physics.train_energy import TrainEnergyProfile, calculate_energy_step
from controllers.energy_controller import ACTIONS, ControllerDecision

logger = logging.getLogger(__name__)

DEBUG_TRAIN_ID = None  # Set to a train's unique_id to trace it, or leave None.

TRAIN_PROFILES = {
    "passenger": {
        "max_speed_kmh": 140,
        "acceleration_ms2": 0.8,
        "deceleration_ms2": 1.2,
        "energy": TrainEnergyProfile(
            mass_kg=420_000, length_m=160, maximum_speed_kmh=140,
            maximum_acceleration_ms2=0.8, maximum_braking_ms2=1.2,
            traction_power_w=4_000_000, rolling_resistance=0.0015,
            aerodynamic_coefficient=0.8, frontal_area_m2=10.0,
            traction_efficiency=0.90, braking_efficiency=0.80,
            auxiliary_power_w=120_000,
        ),
    },
    "freight": {
        "max_speed_kmh": 100,
        "acceleration_ms2": 0.4,
        "deceleration_ms2": 0.8,
        "energy": TrainEnergyProfile(
            mass_kg=1_200_000, length_m=500, maximum_speed_kmh=100,
            maximum_acceleration_ms2=0.4, maximum_braking_ms2=0.8,
            traction_power_w=3_000_000, rolling_resistance=0.0020,
            aerodynamic_coefficient=1.0, frontal_area_m2=12.0,
            traction_efficiency=0.88, braking_efficiency=0.0,
            auxiliary_power_w=60_000,
        ),
    },
}

PRIORITY_BY_TYPE = {"passenger": 2, "freight": 1}

DEGRADED_COMM_SPEED_FACTOR = 0.6
DEGRADED_COMM_SAFETY_EXTRA_M = 500.0

NO_COVERAGE_RAMP_TICKS = 20
NO_COVERAGE_SPEED_FACTOR_START = 0.5
NO_COVERAGE_SPEED_FACTOR_RANGE = 0.3  # Floor = START - RANGE = 0.2.
NO_COVERAGE_SAFETY_EXTRA_START_M = 500.0
NO_COVERAGE_SAFETY_EXTRA_RANGE_M = 1500.0  # Ceiling = START + RANGE = 2000m.

MIN_EFFECTIVE_DECELERATION_MS2 = 0.01
YIELD_PLANNING_BUFFER_M = 2000.0

# Weather configuration
WEATHER_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent / "infrastructure" / "weather_config.json"
)

def load_weather_config():
    """Load weather configuration from JSON file."""
    try:
        with open(WEATHER_CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Default weather config if file not found
        return {
            "weather": {
                "Clear": {"speed_factor": 1.0, "accel_factor": 1.0, "brake_factor": 1.0, "headway_factor": 1.0, "switch_failure_prob_per_hour": 0.0002}
            },
            "current_weather": "Clear"
        }

WEATHER_CONFIG = load_weather_config()


class TrainState(Enum):
    STOPPED = "stopped"
    ACCELERATING = "accelerating"
    CRUISING = "cruising"
    COASTING = "coasting"
    BRAKING = "braking"
    TERMINATED = "terminated"


class TrainAgent(Agent):
    def __init__(self, model, route, graph, train_type="passenger"):
        super().__init__(model)
        self.route      = route
        self.graph      = graph
        self.train_type = train_type

        for i in range(len(route) - 1):
            if not graph.has_edge(route[i], route[i + 1]):
                raise ValueError(
                    f"TrainAgent: no edge between {route[i]} and {route[i+1]} "
                    f"(index {i} -> {i+1})"
                )

        profile = TRAIN_PROFILES.get(train_type, TRAIN_PROFILES["passenger"])
        self.priority = PRIORITY_BY_TYPE.get(train_type, 1)
        self.in_loop = False
        self._pending_loop_arrival = False

        # Store base values for weather application
        self.base_max_speed_ms = profile["max_speed_kmh"] * (1000 / 3600)
        self.base_acceleration_ms2 = profile["acceleration_ms2"]
        self.base_deceleration_ms2 = profile["deceleration_ms2"]
        self.energy_profile = profile["energy"]
        self.current_speed_ms = 0.0
        self.max_speed_reached_kmh = 0.0
        self.current_acceleration_ms2 = 0.0
        self.current_power_w = 0.0
        self.energy_consumed_kwh = 0.0
        self.energy_regenerated_kwh = 0.0
        self.distance_traveled_km = 0.0
        self.operating_time_s = 0.0
        self.energy_by_edge = {}

        self.safety_margin_m = 50.0
        self.arrival_tolerance_m = 1.0

        self.direction = 1 if self._get_node_km(route[-1]) > self._get_node_km(route[0]) else -1
        self.abs_position_km = self._get_node_km(route[0])
        self.state = TrainState.STOPPED

        self.edge_index   = 0
        self.current_node = route[0]
        self.next_node    = route[1] if len(route) > 1 else None
        self.current_edge = None
        self.progress     = 0.0

        self.wait_time    = 0
        self.total_delay_ticks = 0
        self._starvation_boost = False
        self._last_reroute_check_wait = 0

        self._at_station      = True
        self._held_track_edge = None
        self._following_train_id = None
        self._yielding_for_train_id = None
        self.last_decision = "CRUISE"
        self.last_decision_reason = "Baseline rule-based controller has not evaluated this train yet."
        self.last_decision_saving_kwh = 0.0

        self._sync_edge_display()

        self._comm_status = "normal"
        self._comm_candidate = None
        self._comm_candidate_ticks = 0
        self._ticks_since_normal = 0
        self.COMM_UPGRADE_HYSTERESIS = 3

        self.scenario_speed_factor = 1.0
        self.scenario_emergency_stop = False
        self.engine_broken = False

    def _get_node_km(self, node_id):
        return self.model.nodes[node_id].km

    def _current_gradient(self):
        if self.next_node is None:
            return 0.0
        edge = self._get_edge_between(self.current_node, self.next_node)
        return getattr(edge, "gradient", 0.0) if edge is not None else 0.0

    def _get_distance_to_leader(self):
        leader = self.model.get_leading_train(self.abs_position_km, self.direction)
        if not leader:
            return float('inf')
        return abs(leader.abs_position_km - self.abs_position_km) * 1000

    def _get_edge_between(self, node_a, node_b):
        edges = self.graph.get_edge_data(node_a, node_b)
        if not edges:
            return None
        for edge_info in edges.values():
            track_edge = edge_info.get('track_edge')
            if track_edge and track_edge.from_node == node_a and track_edge.to_node == node_b:
                return track_edge
        return None

    def _get_communication_status(self):
        if self._held_track_edge is not None:
            return self._held_track_edge.get_communication_status(self.abs_position_km)

        if self.next_node is not None:
            track_edge = self._get_edge_between(self.current_node, self.next_node)
            if track_edge is not None:
                return track_edge.get_communication_status(self.abs_position_km)

        return "no_coverage"

    def _update_communication_status(self):
        _STATUS_RANK = {"no_coverage": 0, "degraded": 1, "normal": 2}

        raw_status = self._get_communication_status()
        lookahead_status = self._get_lookahead_communication_status()

        if (lookahead_status is not None
            and _STATUS_RANK[lookahead_status] < _STATUS_RANK[raw_status]
            and raw_status == "normal"
            ):
            raw_status = "degraded"


        raw_rank = _STATUS_RANK[raw_status]
        current_rank = _STATUS_RANK[self._comm_status]

        if raw_rank <= current_rank:
            self._comm_status = raw_status
            self._comm_candidate = None
            self._comm_candidate_ticks = 0
        else:
            if raw_status == self._comm_candidate:
                self._comm_candidate_ticks += 1
            else:
                self._comm_candidate = raw_status
                self._comm_candidate_ticks = 1

            if self._comm_candidate_ticks >= self.COMM_UPGRADE_HYSTERESIS:
                self._comm_status = raw_status
                self._comm_candidate = None
                self._comm_candidate_ticks = 0

        if self._comm_status == "normal":
            self._ticks_since_normal = 0
        else:
            self._ticks_since_normal += 1

        return self._comm_status

    def _get_weather_factors(self):
        """Get weather factors from the model's current weather."""
        current_weather = self.model.current_weather
        weather_data = WEATHER_CONFIG.get("weather", {}).get(current_weather, {})

        speed_factor = weather_data.get("speed_factor", 1.0)
        accel_factor = weather_data.get("accel_factor", 1.0)
        brake_factor = weather_data.get("brake_factor", 1.0)

        return speed_factor, accel_factor, brake_factor

    # Movement

    def step(self):
        """Advance movement and account for the resulting energy once."""
        previous_speed_ms = self.current_speed_ms
        previous_position_km = self.abs_position_km
        previous_edge = self.current_edge
        self._step_impl()
        self.distance_traveled_km += abs(self.abs_position_km - previous_position_km)

        duration_s = self.model.time_step * 60
        if self.state != TrainState.TERMINATED:
            self.operating_time_s += duration_s
        self.current_acceleration_ms2 = (
            self.current_speed_ms - previous_speed_ms
        ) / duration_s
        self.max_speed_reached_kmh = max(
            self.max_speed_reached_kmh, self.current_speed_ms * 3.6
        )
        energy_step = calculate_energy_step(
            self.energy_profile,
            max(self.current_speed_ms, previous_speed_ms)
            if self.current_acceleration_ms2 < 0.0
            else self.current_speed_ms,
            self.current_acceleration_ms2,
            duration_s,
            gradient=self._current_gradient(),
            active=self.state != TrainState.TERMINATED,
        )
        self.current_power_w = energy_step.power_w
        self.energy_consumed_kwh += energy_step.power_w * duration_s / 3_600_000
        self.energy_regenerated_kwh += (
            energy_step.regenerated_power_w * duration_s / 3_600_000
        )
        if previous_edge is not None:
            edge_key = f"{previous_edge[0]}-{previous_edge[1]}"
            edge_totals = self.energy_by_edge.setdefault(
                edge_key, {"consumedKwh": 0.0, "regeneratedKwh": 0.0}
            )
            edge_totals["consumedKwh"] += energy_step.power_w * duration_s / 3_600_000
            edge_totals["regeneratedKwh"] += energy_step.regenerated_power_w * duration_s / 3_600_000

    def _step_impl(self):
        if self.state == TrainState.TERMINATED:
            return

        if getattr(self, "scenario_emergency_stop", False):
            self.current_speed_ms = 0.0
            self.state = TrainState.STOPPED
            self._record_wait_tick()
            self._sync_edge_display()
            return

        if getattr(self, "engine_broken", False):
            self.current_speed_ms = 0.0
            self.state = TrainState.STOPPED
            self._record_wait_tick()
            self._sync_edge_display()
            return

        self._maybe_yield_to_faster_follower()
        decision = self.model.controller.decide(self)
        external_action = getattr(self, "external_action", None)
        if external_action in ACTIONS:
            decision = ControllerDecision(
                external_action,
                f"Offline policy proposed {external_action}; railway safety checks remain authoritative.",
            )
        self.last_decision = decision.action
        self.last_decision_reason = decision.reason
        self.last_decision_saving_kwh = decision.estimated_saving_kwh

        if decision.action == "HOLD" and self._at_station:
            self.state = TrainState.STOPPED
            self._record_wait_tick()
            return

        if self._at_station:
            if getattr(self, "_yielding_for_train_id", None) is not None:
                yield_target = self.model._get_agent_by_id(self._yielding_for_train_id)
                passed = yield_target is None or self._train_has_passed(yield_target)
                gave_up = self.wait_time >= self.model.DEADLOCK_WAIT_THRESHOLD

                if passed or gave_up:
                    if gave_up and not passed:
                        logger.warning(
                            "YIELD ABANDONED train=%s at=%s - train=%s never passed after %s t",
                            self.unique_id, self.current_node, self._yielding_for_train_id, self.wait_time
                        )
                    self._yielding_for_train_id = None
                else:
                    logger.info(
                        "YIELD HOLD train=%s at=%s - waiting for train=%s to pass",
                        self.unique_id, self.current_node, self._yielding_for_train_id
                    )
                    self.state = TrainState.STOPPED
                    self._record_wait_tick()
                    return
            switches_at_station = self.model.get_switches(self.current_node)
            if switches_at_station:
                if not self.model.can_proceed_straight(self.current_node):
                    logger.info(
                        "SWITCH FAILURE train=%s at=%s - cannot depart",
                        self.unique_id, self.current_node,
                    )
                    self.state = TrainState.STOPPED
                    self._record_wait_tick()
                    return

            if self.model.get_switches(self.next_node):
                if not self.model.can_proceed_straight(self.next_node):
                    logger.info(
                        "SWITCH CLAMPED train=%s - next station %s switches clamped for diverging, cannot enter straight",
                        self.unique_id, self.next_node,
                    )
                    self.state = TrainState.STOPPED
                    self._record_wait_tick()
                    return

            if self.next_node is not None:
                if self.unique_id not in self.model.cleared_for_departure:
                    logger.info(
                        "DISPATCH HOLD train=%s at=%s - not cleared this tick",
                        self.unique_id, self.current_node,
                    )
                    self.state = TrainState.STOPPED
                    self._record_wait_tick()
                    return

            track_edge = self._get_edge_between(self.current_node, self.next_node)

            if track_edge is not None and track_edge.tracks == 1:
                edge_key_1 = f"{track_edge.from_node}-{track_edge.to_node}"
                edge_key_2 = f"{track_edge.to_node}-{track_edge.from_node}"

                blocked_edges = getattr(self.model,"blocked_edges",set(),)

                if edge_key_1 in blocked_edges or edge_key_2 in blocked_edges:
                    self.state = TrainState.STOPPED
                    self._record_wait_tick()
                    return

                if track_edge.request_clearance(self.unique_id):
                    self._held_track_edge = track_edge
                    self._following_train_id = None
                    self._depart_station()

                elif self._can_follow_occupied_edge(track_edge):
                    lead_id = track_edge.occupied_by
                    self._following_train_id = lead_id
                    self._depart_station()

                else:
                    self.state = TrainState.STOPPED
                    self._record_wait_tick()
                    return
            else:
                self._depart_station()

        edge_end_km = self._get_node_km(self.next_node)

        distance_to_edge_end_m = abs(edge_end_km - self.abs_position_km) * 1000

        if self._following_train_id is not None:
            # Debug trace point for per-tick physics verification
            if DEBUG_TRAIN_ID is not None and self.unique_id == DEBUG_TRAIN_ID:
                pass  # Per-tick details logged at end of step() after physics applied

            lead_train = self.model._get_agent_by_id(self._following_train_id)

            if lead_train is not None and lead_train.state.value != "terminated":
                distance_to_leader_m = abs(
                    lead_train.abs_position_km - self.abs_position_km
                ) * 1000
            else:
                self._following_train_id = None
                distance_to_leader_m = float("inf")
        else:
            distance_to_leader_m = self._get_distance_to_leader()

        available_distance_m = min(distance_to_edge_end_m, distance_to_leader_m)

        # Communication status affects speed and safety margins
        comm_status = self._update_communication_status()
        comm_speed_factor, safety_extra_m = self._get_speed_and_safety_factors(comm_status)

        # Apply weather factors
        weather_speed_factor, weather_accel_factor, weather_brake_factor = self._get_weather_factors()

        # Combine communication and weather factors
        current_edge = self._get_edge_between(self.current_node, self.next_node)
        edge_speed_limit_ms = self.base_max_speed_ms
        if current_edge is not None:
            edge_speed_limit_ms = min(edge_speed_limit_ms, current_edge.speed_limit_kmh / 3.6)
        effective_max_speed_ms = min(
            edge_speed_limit_ms * weather_speed_factor * comm_speed_factor
            * getattr(self, "scenario_speed_factor", 1.0),
            self.base_max_speed_ms,
        )
        effective_acceleration_ms2 = self.base_acceleration_ms2 * weather_accel_factor
        effective_deceleration_ms2 = max(
            self.base_deceleration_ms2 * weather_brake_factor,
            MIN_EFFECTIVE_DECELERATION_MS2,
        )
        effective_safety_margin_m = self.safety_margin_m + safety_extra_m

        braking_distance_m = (self.current_speed_ms ** 2) / (2 * effective_deceleration_ms2)
        safe_distance_to_leader_m = braking_distance_m + effective_safety_margin_m
        time_step_s = self.model.time_step * 60

        if self._has_reached_edge_end(edge_end_km):
            self._arrive_at_next_station(edge_end_km)
            self._sync_edge_display()
            return

        should_brake_for_station = distance_to_edge_end_m <= braking_distance_m
        should_brake_for_leader = distance_to_leader_m <= safe_distance_to_leader_m

        if should_brake_for_station or should_brake_for_leader or decision.action == "BRAKE":
            self.current_speed_ms -= effective_deceleration_ms2 * time_step_s
            self.current_speed_ms = max(0.0, self.current_speed_ms)
            self.state = TrainState.BRAKING if self.current_speed_ms > 0 else TrainState.STOPPED
        elif decision.action == "COAST" and self.current_speed_ms > 0.0:
            self.state = TrainState.COASTING
        elif self.current_speed_ms < effective_max_speed_ms:
            self.state = TrainState.ACCELERATING
            self.current_speed_ms += effective_acceleration_ms2 * time_step_s
            self.current_speed_ms = min(self.current_speed_ms, effective_max_speed_ms)
        else:
            self.state = TrainState.CRUISING

        distance_traveled_m = self.current_speed_ms * time_step_s
        if distance_traveled_m + self.arrival_tolerance_m >= distance_to_edge_end_m:
            self.abs_position_km = edge_end_km
        else:
            self.abs_position_km += (distance_traveled_m / 1000.0) * self.direction

        if self._following_train_id is not None:
            lead_train = self.model._get_agent_by_id(self._following_train_id)

            if lead_train is not None and lead_train.state != TrainState.TERMINATED:

                if lead_train._at_station:
                    self._following_train_id = None
                else:
                    lead_position = lead_train.abs_position_km
                    safety_distance_km = self.safety_margin_m / 1000.0

                    if self.direction == 1:
                        max_position = lead_position - safety_distance_km

                        if self.abs_position_km >= max_position:
                            self.abs_position_km = max_position
                            self.current_speed_ms = min(
                                self.current_speed_ms,
                                lead_train.current_speed_ms
                            )
                            self.state = TrainState.BRAKING
                    else:
                        min_position = lead_position + safety_distance_km

                        if self.abs_position_km <= min_position:
                            self.abs_position_km = min_position
                            self.current_speed_ms = min(
                                self.current_speed_ms,
                                lead_train.current_speed_ms
                            )
                            self.state = TrainState.BRAKING

        if DEBUG_TRAIN_ID is not None and self.unique_id == DEBUG_TRAIN_ID:
            # Get leader's position for comparison
            leader_pos_km = None
            if self._following_train_id is not None:
                lead_train = self.model._get_agent_by_id(self._following_train_id)
                if lead_train is not None:
                    leader_pos_km = lead_train.abs_position_km
            logger.info(
                "TRAIN%s pos=%.3f km speed=%.1f km/h state=%s edge_end=%.3f dist_to_leader=%.1fm avail=%.1fm following=%s leader_pos=%.3f km",
                self.unique_id, self.abs_position_km, self.current_speed_ms * 3.6, self.state.value,
                edge_end_km, distance_to_leader_m, available_distance_m, self._following_train_id,
                leader_pos_km if leader_pos_km is not None else 0.0,
            )

        if self._has_reached_edge_end(edge_end_km):
            self._arrive_at_next_station(edge_end_km)

        self._sync_edge_display()

    def _has_reached_edge_end(self, edge_end_km):
        tolerance_km = self.arrival_tolerance_m / 1000.0
        if math.isclose(self.abs_position_km, edge_end_km, abs_tol=tolerance_km):
            return True
        return self.direction * (self.abs_position_km - edge_end_km) > 0

    def _arrive_at_next_station(self, edge_end_km):
        self._following_train_id = None
        self.abs_position_km = edge_end_km
        self.current_speed_ms = 0.0

        self._release_held_track_edge()

        self.edge_index += 1
        self.current_node = self.next_node
        self.next_node = (
            self.route[self.edge_index + 1]
            if self.edge_index + 1 < len(self.route) else None
        )

        if self._pending_loop_arrival:
            self.model.enter_loop(self.current_node, self.unique_id)
            self.in_loop = True
            self._pending_loop_arrival = False

        if self.next_node is None:
            self.state = TrainState.TERMINATED
            self._at_station = False
        else:
            self._at_station = True
            self.state = TrainState.STOPPED

    def _sync_edge_display(self):
        if self.next_node is None:
            self.current_edge = None
            self.progress = 1.0
            return

        km_a = self._get_node_km(self.current_node)
        km_b = self._get_node_km(self.next_node)
        lo_km, hi_km = (km_a, km_b) if km_a <= km_b else (km_b, km_a)

        self.current_edge = (
            (self.current_node, self.next_node) if km_a <= km_b
            else (self.next_node, self.current_node)
        )
        edge_length = hi_km - lo_km
        self.progress = (self.abs_position_km - lo_km) / edge_length if edge_length > 0 else 0.0

    def _release_held_track_edge(self):
        held = self._held_track_edge
        if held is not None:
            held.release_clearance(self.unique_id)
        self._held_track_edge = None

    def _get_speed_and_safety_factors(self, comm_status):
        if comm_status == "normal":
            return 1.0, 0

        if comm_status == "degraded":
            return DEGRADED_COMM_SPEED_FACTOR, DEGRADED_COMM_SAFETY_EXTRA_M

        ticks_out = min(self._ticks_since_normal, NO_COVERAGE_RAMP_TICKS)
        severity = ticks_out / NO_COVERAGE_RAMP_TICKS  # 0.0 -> 1.0

        speed_factor = (
            NO_COVERAGE_SPEED_FACTOR_START
            - (NO_COVERAGE_SPEED_FACTOR_RANGE * severity)
        )
        # Safety margin grows from 500m up to 2000m the longer we're blind
        safety_extra_m = (
            NO_COVERAGE_SAFETY_EXTRA_START_M
            + (NO_COVERAGE_SAFETY_EXTRA_RANGE_M * severity)
        )

        return speed_factor, safety_extra_m

    LOOKAHEAD_KM = 1.5

    def _get_lookahead_communication_status(self):
        edge = self._held_track_edge
        if edge is None and self.next_node is not None:
            edge = self._get_edge_between(self.current_node, self.next_node)
        if edge is None:
            return None

        probe_km = self.abs_position_km + (self.LOOKAHEAD_KM * self.direction)
        return edge.get_communication_status(probe_km)

    def _can_follow_occupied_edge(self, track_edge):
        if track_edge is None or track_edge.tracks != 1:
            return False

        lead_id = track_edge.occupied_by
        if lead_id is None or lead_id == self.unique_id:
            return False
        if self.train_type != "passenger":
            return False

        lead_train = self.model._get_agent_by_id(lead_id)
        if lead_train is None or lead_train.state.value == "terminated":
            return False
        if lead_train.train_type != "freight":
            return False

        return lead_train.direction == self.direction

    def _train_has_passed(self, other):
        if other.state.value == "terminated":
            return True
        return self.direction * (other.abs_position_km - self.abs_position_km) > 0

    def _maybe_yield_to_faster_follower(self):
        if self._at_station or self.in_loop or self.next_node is None:
            return
        if self._yielding_for_train_id is not None:
            return

        follower = self.model.get_following_train(self.abs_position_km, self.direction)
        if follower is None or follower.direction != self.direction or follower.priority <= self.priority:
            return
        if not self.model.station_has_free_loop(self.next_node):
            return

        gap_m = abs(follower.abs_position_km - self.abs_position_km) * 1000
        follower_braking_m = (follower.current_speed_ms ** 2) / (
            2 * max(follower.base_deceleration_ms2, MIN_EFFECTIVE_DECELERATION_MS2)
        )
        yield_trigger_m = follower_braking_m + follower.safety_margin_m + YIELD_PLANNING_BUFFER_M

        if gap_m <= yield_trigger_m:
            self._pending_loop_arrival = True
            self._yielding_for_train_id = follower.unique_id
            logger.info(
                "YIELD PLANNED train=%s will duck into loop at %s for train=%s (gap=%.0fm, trigger=%.0fm)",
                self.unique_id, self.next_node, follower.unique_id, gap_m, yield_trigger_m,
            )

    def _depart_station(self):
        self._at_station = False
        self.wait_time = 0
        self._last_reroute_check_wait = 0
        self._starvation_boost = False
        if self.in_loop:
            self.model.exit_loop(self.current_node, self.unique_id)
            self.in_loop = False

    def reroute(self, new_route):
        if new_route[0] != self.current_node:
            raise ValueError("new_route must start at the trains current node")
        traveled = self.route[:self.edge_index]
        self.route = traveled + new_route
        self.next_node = new_route[1] if len(new_route) > 1 else None
        self._last_reroute_check_wait = 0
        self._sync_edge_display()


    def clear_emergency_stop(self):
        if self.scenario_emergency_stop:
            logger.info("Emergency stop cleared train=%s - reassessing", self.unique_id)
        self.scenario_emergency_stop = False

    def repair_engine(self):
        if self.engine_broken:
                    logger.info("Engine repared train=%s - reassessing", self.unique_id)
        self.engine_broken = False

    def clear_train_speed_restriction(self):
        self.scenario_speed_factor = 1.0

    def _record_wait_tick(self):
        self.wait_time += 1
        self.total_delay_ticks += 1

    # Status

    def get_status(self):
        return {
            "train_id":       self.unique_id,
            "current_node":   self.current_node,
            "next_node":      self.next_node,
            "progress":       self.progress,
            "current_edge":   self.current_edge,
            "edge_index":     self.edge_index,
            "route":          self.route,
            "wait_time":      self.wait_time,
            "total_delay_ticks": self.total_delay_ticks,
            "train_type":     self.train_type,
            "state":          self.state.value if hasattr(self.state, 'value') else str(self.state),
            "abs_position_km": self.abs_position_km,
            "direction":      self.direction,
            "speed_kmh":      self.current_speed_ms * 3.6,
            "current_acceleration_ms2": self.current_acceleration_ms2,
            "power_w":         self.current_power_w,
            "energy_consumed_kwh": self.energy_consumed_kwh,
            "energy_regenerated_kwh": self.energy_regenerated_kwh,
            "net_energy_kwh": self.energy_consumed_kwh - self.energy_regenerated_kwh,
            "distance_traveled_km": self.distance_traveled_km,
            "controller_action": self.last_decision,
            "controller_reason": self.last_decision_reason,
            "estimated_saving_kwh": self.last_decision_saving_kwh,
            "energy_by_edge": self.energy_by_edge,
            "mass_kg":         self.energy_profile.mass_kg,
            "length_m":        self.energy_profile.length_m,
            "at_station":     self._at_station,
            "in_loop":        self.in_loop,
        }
