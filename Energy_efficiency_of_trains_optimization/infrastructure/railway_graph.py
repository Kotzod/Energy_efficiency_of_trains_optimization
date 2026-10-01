import logging
import bisect
import json
import os
import networkx as nx

from mesa import Model, DataCollector
from mesa.space import NetworkGrid

from agents.train_agent import TrainAgent
from infrastructure.graph_builder import build_graph
from infrastructure.node import Node
from infrastructure.radiotower import RadioTower
from infrastructure.switch import can_use_passing_loop, can_proceed_straight
from controllers.energy_controller import MPCController, RuleBasedController
from controllers.rl_controller import RLController

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

# ── Routes ────────────────────────────────────────────────────────────────────

WESTBOUND = [
    "TPE", "LLH", "TSO", "KAU", "NOA", "SIU", "SNM", "KRU",
    "HNO", "VMA", "AS",  "AHV", "KKI", "HVA", "NAL", "ULV", "PRI",
]
EASTBOUND = list(reversed(WESTBOUND))

# spawn_tick: simulation minute at which this train departs
SCHEDULES = [
    {"route": WESTBOUND, "type": "passenger", "spawn_tick": 0},
    {"route": EASTBOUND, "type": "freight",   "spawn_tick": 0},
    {"route": WESTBOUND, "type": "freight",   "spawn_tick": 20},
    {"route": EASTBOUND, "type": "passenger", "spawn_tick": 30},
]


class RailwayModel(Model):
    """Mesa model for the Tampere-Pori railway corridor."""

    def __init__(self, time_step_minutes: int = 1, seed: int | None = None):
        super().__init__(seed=seed)
        self.time_step = time_step_minutes
        self.simulation_time = 0
        self.steps = 0
        self.pending_mutations = []
        self.controller_mode = "rule_based"
        self.controller = RuleBasedController()

        # Load weather configuration
        weather_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "weather_config.json")
        try:
            with open(weather_config_path, encoding="utf-8") as f:
                weather_config = json.load(f)
            weather_by_name = weather_config.get("weather", {})
            if isinstance(weather_by_name, dict) and weather_by_name:
                default_weather = "Clear" if "Clear" in weather_by_name else next(iter(weather_by_name))
                self.current_weather = weather_config.get("current_weather", default_weather)
                if self.current_weather not in weather_by_name:
                    self.current_weather = default_weather
            else:
                self.current_weather = "Clear"
        except (FileNotFoundError, json.JSONDecodeError):
            self.current_weather = "Clear"

        self.graph = build_graph()
        self.grid  = NetworkGrid(self.graph)

        self.nodes: dict = {
            node_id: self.graph.nodes[node_id]['node_object']
            for node_id in self.graph.nodes()
        }

        self.switches: dict = self.graph.graph.get('switches', {})

        self.radio_towers = self._build_radio_towers()
        self._attach_radio_towers_to_edges()

        # Spatial indices mapping direction to a sorted list of tuples: (abs_position_km, agent)
        self.spatial_index = {
            1: [],  # Westbound (Tampere -> Pori)
            -1: []  # Eastbound (Pori -> Tampere)
        }

        self.cleared_for_departure = set()
        self.loop_occupancy = {}
        self.station_occupancy = {}
        self.DEADLOCK_WAIT_THRESHOLD = 15
        self.REROUTE_WAIT_THRESHOLD = 8
        self.REROUTE_RETRY_INTERVAL = 5

        self.datacollector = DataCollector(
            model_reporters={
                "sim_time":      "simulation_time",
                "active_trains": lambda m: sum(
                    1 for a in m.agents if a.state.value != "terminated"
                ),
                "trains_waiting": lambda m: sum(
                    1 for a in m.agents if a.state.value == "stopped"
                ),
                "trains_in_starvation_recovery": lambda m: sum(
                    1 for a in m.agents if getattr(a, "_starvation_boost", False)
                ),
                "blocked_edges_count": lambda m: len(getattr(m, "blocked_edges", set())),
                "total_delay_ticks": lambda m: sum(
                    getattr(a, "total_delay_ticks", 0) for a in m.agents
                ),
            },
            agent_reporters={
                "state":      lambda a: a.state.value,
                "node":       "current_node",
                "next_node":  "next_node",
                "progress":   "progress",
                "edge":       lambda a: str(a.current_edge),
                "wait_time":  "wait_time",
                "total_delay_ticks": "total_delay_ticks",
                "train_type": "train_type",
            },
        )

        self._schedules = list(SCHEDULES)
        self._spawn_due_trains()

    def set_controller_mode(self, mode: str):
        """Select a driving policy; infrastructure safety remains unchanged."""
        if mode not in {"rule_based", "mpc", "ai"}:
            raise ValueError("controller mode must be 'rule_based', 'mpc', or 'ai'")
        self.controller_mode = mode
        if mode == "mpc":
            self.controller = MPCController()
        elif mode == "ai":
            self.controller = RLController("training/checkpoints/railway_ppo")
        else:
            self.controller = RuleBasedController()

    # Spawning

    def _spawn_due_trains(self):
        remaining = []
        for entry in self._schedules:
            if self.simulation_time >= entry["spawn_tick"]:
                try:
                    train = TrainAgent(
                        model=self,
                        route=entry["route"],
                        graph=self.graph,
                        train_type=entry["type"],
                    )
                    self.grid.place_agent(train, entry["route"][0])
                    logger.info(
                        "Spawned %s train %s at %s (tick %s)",
                        entry["type"], train.unique_id,
                        entry["route"][0], self.simulation_time,
                    )
                except ValueError as e:
                    logger.error("Failed to spawn train: %s", e)
            else:
                remaining.append(entry)
        self._schedules = remaining

    # Spatial Index

    def _update_spatial_index(self):
        """Rebuilds the sorted spatial index for active trains every tick."""
        self.spatial_index[1].clear()
        self.spatial_index[-1].clear()

        for agent in self.agents:
            if hasattr(agent, 'state') and agent.state.value != "terminated":
                self.spatial_index[agent.direction].append((agent.abs_position_km, agent))

        self.spatial_index[1].sort(key=lambda x: x[0])
        self.spatial_index[-1].sort(key=lambda x: x[0])

    def _update_station_occupancy(self):
        """Platform occupancy per station -- excludes trains parked in a loop,
        since the loop is a separate resource with its own capacity of 1."""
        self.station_occupancy = {}
        for agent in self.agents:
            if agent.state.value == "terminated":
                continue
            if agent._at_station and not agent.in_loop:
                self.station_occupancy.setdefault(agent.current_node, set()).add(agent.unique_id)

    def _get_station_capacity(self, station_id: str) -> int:
        node_data = self.graph.nodes.get(station_id, {})
        return node_data.get("station_capacity", 0)

    def station_has_free_loop(self, station_id: str) -> bool:
        node_data = self.graph.nodes.get(station_id, {})
        if not node_data.get("passing_loop", False):
            return False
        return self.loop_occupancy.get(station_id) is None

    def enter_loop(self, station_id: str, train_id) -> bool:
        if not self.station_has_free_loop(station_id):
            return False
        self.loop_occupancy[station_id] = train_id
        return True

    def exit_loop(self, station_id: str, train_id):
        if self.loop_occupancy.get(station_id) == train_id:
            self.loop_occupancy[station_id] = None

    def _reserve_destination_room(self, agent, reserved_platform, reserved_loop) -> bool:
        """
        Approach control: a train may only be cleared to depart if its
        destination has room -- either an open platform slot, or (if the
        platform is full) a free passing loop it can be parked in.
        """
        next_node = agent.next_node
        capacity = self._get_station_capacity(next_node)
        if capacity <= 0:
            return True

        occupants = len(self.station_occupancy.get(next_node, set()))
        already_reserved = reserved_platform.get(next_node, 0)

        if occupants + already_reserved < capacity:
            reserved_platform[next_node] = already_reserved + 1
            return True

        if next_node not in reserved_loop and self.station_has_free_loop(next_node):
            reserved_loop.add(next_node)
            agent._pending_loop_arrival = True
            return True

        return False

    def _can_passenger_follow_freight_on_occupied_edge(self, agent, edge):
        if edge is None:
            return False
        return agent._can_follow_occupied_edge(edge)

    def _resolve_departures(self):
        self._update_station_occupancy()
        self.cleared_for_departure = set()

        candidates = [
            a for a in self.agents
            if a.state.value != "terminated" and a._at_station and a.next_node is not None
        ]

        candidates.sort(
            key=lambda a: (
                0 if getattr(a, "_starvation_boost", False) else 1,
                0 if a.train_type == "passenger" else 1,
                -a.wait_time,
            )
        )

        claimed_edges = set()
        reserved_platform = {}
        reserved_loop = set()
        contention_losers = []

        for agent in candidates:
            edge = agent._get_edge_between(agent.current_node, agent.next_node)

            blocked_edges=getattr(self, "blocked_edges", set())
            if edge is not None:
                ek1 = f"{edge.from_node}-{edge.to_node}"
                ek2 = f"{edge.to_node}-{edge.from_node}"
                if ek1 in blocked_edges or ek2 in blocked_edges:
                    continue

            follow_same_direction = self._can_passenger_follow_freight_on_occupied_edge(agent, edge)

            edge_key = None

            if edge is not None and edge.tracks == 1:
                logger.info(
                    "Dispatch check train=%s type=%s edge=%s->%s occupied_by=%s follow=%s",
                    agent.unique_id, agent.train_type, edge.from_node, edge.to_node, edge.occupied_by, follow_same_direction,
                )
                edge_key = frozenset([id(edge), id(edge.opposite)]) if edge.opposite else id(edge)
                if edge_key in claimed_edges and not follow_same_direction:
                    contention_losers.append(agent)
                    continue

            if not self._reserve_destination_room(agent, reserved_platform, reserved_loop):
                logger.info(
                    "DISPATCH HOLD train=%s at=%s - destination %s at capacity",
                    agent.unique_id, agent.current_node, agent.next_node,
                )
                continue

            if edge_key is not None:
                claimed_edges.add(edge_key)
            self.cleared_for_departure.add(agent.unique_id)

        for agent in contention_losers:
            if agent.in_loop:
                continue
            if self.enter_loop(agent.current_node, agent.unique_id):
                agent.in_loop = True
                logger.info(
                    "DISPATCH: train=%s diverted into passing loop at %s (yielding priority)",
                    agent.unique_id, agent.current_node,
                )

    def _track_edge_is_usable(self, track_edge, train, from_node, to_node):
        edge_key1 = f"{track_edge.from_node}-{track_edge.to_node}"
        edge_key2 = f"{track_edge.to_node}-{track_edge.from_node}"
        blocked_edges = getattr(self, "blocked_edges", set())
        if edge_key1 in blocked_edges or edge_key2 in blocked_edges:
            return False

        if track_edge.tracks != 1:
            return True

        if track_edge.from_node != from_node or track_edge.to_node != to_node:
            return False

        if track_edge.opposite and track_edge.opposite.occupied_by not in (None, train.unique_id):
            return False

        if track_edge.occupied_by is None or track_edge.occupied_by == train.unique_id:
            return True

        return train._can_follow_occupied_edge(track_edge)

    def _edge_weight_for_train(self, train):
        def _weight(u, v, edge_dict):
            if not self.can_proceed_straight(u) or not self.can_proceed_straight(v):
                return None

            best = None
            for data in edge_dict.values():
                track_edge = data.get("track_edge")
                if track_edge is None:
                    continue
                if not self._track_edge_is_usable(track_edge, train, u, v):
                    continue
                if best is None or track_edge.distance_km < best:
                    best = track_edge.distance_km
            return best
        return _weight

    def find_alternative_route(self, train):
        destination = train.route[-1]
        if train.current_node == destination:
            return None

        try:
            candidate = nx.shortest_path(
                self.graph, train.current_node, destination,
                weight=self._edge_weight_for_train(train),
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

        remaining_planned = train.route[train.edge_index:]
        if candidate == remaining_planned:
            return None

        return candidate

    def _check_for_deadlocks(self):
        for agent in self.agents:
            if agent.state.value != "stopped" or agent.wait_time < self.REROUTE_WAIT_THRESHOLD:
                continue
            if getattr(agent, "scenario_emergency_stop", False) or getattr(agent, "engine_broken", False):
                continue

            ticks_since_check = agent.wait_time - agent._last_reroute_check_wait
            if agent._last_reroute_check_wait == 0 or ticks_since_check >= self.REROUTE_RETRY_INTERVAL:
                agent._last_reroute_check_wait = agent.wait_time
                alternative = self.find_alternative_route(agent)
                if alternative is not None:
                    agent.reroute(alternative)
                    logger.warning(
                        "REROUTE: train=%s stuck at %s for %s ticks - rerouted via %s",
                        agent.unique_id, agent.current_node, agent.wait_time, alternative,
                    )
                    continue

            if agent.wait_time < self.DEADLOCK_WAIT_THRESHOLD:
                continue
            if not self.can_proceed_straight(agent.current_node):
                continue  # switch failure, already logged elsewhere
            if not getattr(agent, "_starvation_boost", False):
                agent._starvation_boost = True
                logger.warning(
                    "STARVATION recovery: train=%s stuck at %s for %s ticks - prioroty boosted",
                    agent.unique_id, agent.current_node, agent.wait_time,
                )

    def _get_agent_by_id(self, agent_id):
        for agent in self.agents:
            if agent.unique_id == agent_id:
                return agent
        return None

    def get_leading_train(self, current_km: float, direction: int):
        index_list = self.spatial_index.get(direction, [])
        if not index_list:
            return None

        km_keys = [item[0] for item in index_list]

        insertion_point = bisect.bisect_right(km_keys, current_km)

        if direction == 1:
            if insertion_point < len(index_list):
                leader = index_list[insertion_point][1]
                if leader.abs_position_km > current_km:
                    return leader
        else:
            insertion_point = bisect.bisect_left(km_keys, current_km)
            if insertion_point > 0:
                leader = index_list[insertion_point - 1][1]
                if leader.abs_position_km < current_km:
                    return leader

        return None

    def get_following_train(self, current_km: float, direction: int):
        index_list = self.spatial_index.get(direction, [])
        if not index_list:
            return None

        km_keys = [item[0] for item in index_list]

        if direction == 1:
            insertion_point = bisect.bisect_left(km_keys, current_km)
            if insertion_point > 0:
                follower = index_list[insertion_point - 1][1]
                if follower.abs_position_km < current_km:
                    return follower
        else:
            insertion_point = bisect.bisect_right(km_keys, current_km)
            if insertion_point < len(index_list):
                follower = index_list[insertion_point][1]
                if follower.abs_position_km > current_km:
                    return follower

        return None

    # Step

    def get_energy_metrics(self) -> dict:
        """Return measured energy and traffic metrics for active train agents."""
        trains = list(self.agents)
        active = [train for train in trains if train.state.value != "terminated"]
        moving = [train for train in active if train.current_speed_ms > 1e-6]
        stopped = [train for train in active if train.current_speed_ms <= 1e-6]
        total_consumed = sum(train.energy_consumed_kwh for train in trains)
        total_regenerated = sum(train.energy_regenerated_kwh for train in trains)
        total_distance = sum(train.distance_traveled_km for train in trains)
        total_operating_time_s = sum(train.operating_time_s for train in trains)
        total_net = total_consumed - total_regenerated

        return {
            "totalPowerW": sum(train.current_power_w for train in active),
            "totalEnergyConsumedKwh": total_consumed,
            "totalEnergyRegeneratedKwh": total_regenerated,
            "totalNetEnergyKwh": total_net,
            "averageSpeedKmh": (
                total_distance / (total_operating_time_s / 3600.0)
                if total_operating_time_s > 0.0 else 0.0
            ),
            "activeTrains": len(active),
            "movingTrains": len(moving),
            "stoppedTrains": len(stopped),
            "totalDelayTicks": sum(train.total_delay_ticks for train in trains),
            "trainsHolding": sum(
                1 for train in active
                if getattr(train, "_yielding_for_train_id", None) is not None
                or getattr(train, "_yielding_for_oncoming_id", None) is not None
            ),
            "energyPerKm": total_net / total_distance if total_distance > 0 else 0.0,
            "totalDistanceKm": total_distance,
            "peakSpeedKmh": max(
                (train.max_speed_reached_kmh for train in trains),
                default=0.0,
            ),
            "controllerMode": self.controller_mode,
            "energyByEdge": self.get_energy_by_edge(),
        }

    def get_energy_by_edge(self) -> dict:
        totals = {}
        for train in self.agents:
            for edge_key, values in getattr(train, "energy_by_edge", {}).items():
                current = totals.setdefault(edge_key, {"consumedKwh": 0.0, "regeneratedKwh": 0.0})
                current["consumedKwh"] += values["consumedKwh"]
                current["regeneratedKwh"] += values["regeneratedKwh"]
                current["netKwh"] = current["consumedKwh"] - current["regeneratedKwh"]
        return totals

    def step(self):
        self._spawn_due_trains()
        self._update_spatial_index()
        self.apply_pending_mutations()
        self._update_switch_operational_time()
        self._resolve_departures()
        self.simulation_time += self.time_step
        self.agents.shuffle_do("step")
        self.datacollector.collect(self)
        self._check_for_deadlocks()

    def apply_pending_mutations(self):
        current_tick = self.simulation_time
        remaining = []

        try:
            from frontend.nlp.prompt_parser import apply_single_mutation
        except ImportError:
            from nlp.prompt_parser import apply_single_mutation

        for item in self.pending_mutations:
            if item["trigger_tick"] <= current_tick:
                apply_single_mutation(
                    self,
                    item["category"],
                    item["mutation"],
                )
            else:
                remaining.append(item)

        self.pending_mutations = remaining

    def _update_switch_operational_time(self):
        hours = self.time_step / 60.0
        for switches in self.switches.values():
            for switch in switches:
                switch.update_operational_time(
                    hours,
                    current_weather=self.current_weather,
                    rng=self.random,
                )

    # Helpers

    def _build_radio_towers(self) -> dict:
        base = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(base, "radio_towers.json")

        if not os.path.exists(json_path):
            logger.warning("No radio tower file found at %s", json_path)
            return {}

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        towers = {}
        for tower_data in data.get("radio_towers", []):
            tower = RadioTower(
                tower_id=tower_data["tower_id"],
                position_km=tower_data.get("position_km", 0.0),
                radius_km=tower_data.get("radius_km", 2.4),
            )

            if tower.tower_id in towers:
                raise ValueError(f"Duplicate radio tower id: {tower.tower_id}")

            towers[tower.tower_id] = tower

        return towers

    def _attach_radio_towers_to_edges(self):
        for _, _, _, data in self.graph.edges(keys=True, data=True):
            edge = data.get("track_edge")
            if edge is None:
                continue

            from_km = self.nodes[edge.from_node].km
            to_km = self.nodes[edge.to_node].km

            edge_start = min(from_km, to_km)
            edge_end = max(from_km, to_km)

            for tower in self.radio_towers.values():
                tower_start = tower.position_km - tower.radius_km
                tower_end = tower.position_km + tower.radius_km

                if tower_end >= edge_start and tower_start <= edge_end:
                    edge.add_radio_tower(tower)

    def get_node(self, node_id: str) -> Node:
        return self.nodes.get(node_id)

    def get_switches(self, station_id: str) -> list:
        return self.switches.get(station_id, [])

    def can_use_passing_loop(self, station_id: str, train_id=None) -> bool:
        return can_use_passing_loop(self.get_switches(station_id), train_id)

    def can_proceed_straight(self, station_id: str) -> bool:
        return can_proceed_straight(self.get_switches(station_id))

    def fail_station_switches(self, station_id: str):
        for switch in self.get_switches(station_id):
            switch.fail()

    def repair_station_switches(self, station_id: str):
        for switch in self.get_switches(station_id):
            switch.repair()

    def fail_switch(self, station_id: str, switch_index: int):
        switches = self.get_switches(station_id)
        if 0 <= switch_index < len(switches):
            switches[switch_index].fail()

    def repair_switch(self, station_id: str, switch_index: int):
        switches = self.get_switches(station_id)
        if 0 <= switch_index < len(switches):
            switches[switch_index].repair()

    def clamp_switch(self, station_id: str, switch_index: int, position: str = "normal"):
        switches = self.get_switches(station_id)
        if 0 <= switch_index < len(switches):
            switches[switch_index].clamp(position)

    def release_switch_clamp(self, station_id: str, switch_index: int):
        switches = self.get_switches(station_id)
        if 0 <= switch_index < len(switches):
            switches[switch_index].release_clamp()

    def get_switch_statuses(self) -> list:
        statuses = []
        for station_id, switches in self.switches.items():
            for sw in switches:
                statuses.append({
                    "station_id": station_id,
                    "switch_id": sw.switch_id,
                    "failed": sw.failed,
                    "clamped": sw.clamped,
                    "clamped_position": sw.clamped_position,
                    "available": sw.is_available(),
                    "allows_straight": sw.allows_straight(),
                    "allows_diverging": sw.allows_diverging(),
                })
        return statuses

    def fail_radio_tower(self, tower_id: str):
        tower = self.radio_towers.get(tower_id)
        if tower is None:
            raise KeyError(f"Unknown radio tower: {tower_id}")
        tower.fail()

    def repair_radio_tower(self, tower_id: str):
        tower = self.radio_towers.get(tower_id)
        if tower is None:
            raise KeyError(f"Unknown radio tower: {tower_id}")
        tower.repair()

    def get_radio_tower_statuses(self) -> list:
        return [
            tower.get_status()
            for tower in self.radio_towers.values()
        ]

    def unblock_edge(self, edge_key: str):
        if hasattr(self, "blocked_edges"):
            self.blocked_edges.discard(edge_key)

    def clear_dispatch_hold(self, target_id: str):
        if hasattr(self, "dispatch_holds"):
            self.dispatch_holds.discard(target_id)

    def clear_train_emergency_stop(self, train_id):
        agent = self._get_agent_by_id(train_id)
        if agent is None:
            raise KeyError(f"Unknown train: {train_id}")
        agent.clear_emergency_stop()

    def repair_train_engine(self, train_id):
        agent = self._get_agent_by_id(train_id)
        if agent is None:
            raise KeyError(f"Unknown train: {train_id}")
        agent.repair_engine()


    def clear_train_speed_restriction(self, train_id):
        agent = self._get_agent_by_id(train_id)
        if agent is None:
            raise KeyError(f"Unknown train: {train_id}")
        agent.clear_speed_restriction()