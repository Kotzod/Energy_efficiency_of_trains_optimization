"""
Shared application state management.

Holds the single RailwayModel instance with thread-safe locking for access.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

from infrastructure.railway_graph import RailwayModel
from backend.positioning import PositioningEngine


class AppState:
    """Global application state with thread-safe access to the shared model."""

    def __init__(self, repo_root: Path):
        """
        Initialize app state with a fresh RailwayModel.

        Args:
            repo_root: Path to repository root
        """
        self.repo_root = Path(repo_root)
        self.lock = asyncio.Lock()

        # Initialize positioning engine (reads infrastructure JSON once)
        self.positioning = PositioningEngine(repo_root)

        # Initialize fresh model with default seed
        self.model = RailwayModel(seed=67)
        self.tick = 0
        self.running = False

        # Cache tower heatmap points (static per tower)
        self._update_tower_cache()

        # Load weather config
        self.weather_config = self._load_weather_config()

    def _update_tower_cache(self):
        """Rebuild tower heatmap point cache."""
        self.tower_geo_cache = {
            tower_id: self.positioning.build_tower_geo_points(tower)
            for tower_id, tower in self.model.radio_towers.items()
        }

    def _load_weather_config(self) -> Dict[str, Any]:
        """Load weather configuration from JSON."""
        weather_config_path = self.repo_root / "infrastructure" / "weather_config.json"
        try:
            with open(weather_config_path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"weather": {"Clear": {"symbol": "☀️"}}}

    async def step(self):
        """Execute one simulation step with lock."""
        async with self.lock:
            self.model.step()
            self.tick += 1

    async def reset(self, seed: int = 67):
        """Reset model to initial state with optional seed."""
        async with self.lock:
            self.model = RailwayModel(seed=seed)
            self.tick = 0
            self.running = False
            self._update_tower_cache()

    async def set_scenario(self, new_model: RailwayModel):
        """Replace the current model with a new one (from scenario parsing)."""
        async with self.lock:
            self.model = new_model
            self.tick = 0
            self.running = False
            self._update_tower_cache()

    async def get_status(self) -> Dict[str, Any]:
        """Get current infrastructure status snapshot."""
        async with self.lock:
            return {
                "weather": getattr(self.model, "current_weather", "Clear"),
                "blockedEdges": sorted(getattr(self.model, "blocked_edges", set())),
                "dispatchHolds": sorted(getattr(self.model, "dispatch_holds", set())),
                "towers": self.model.get_radio_tower_statuses(),
                "switches": self.model.get_switch_statuses(),
                "controllerMode": self.model.controller_mode,
            }

    async def set_controller_mode(self, mode: str) -> str:
        async with self.lock:
            self.model.set_controller_mode(mode)
            return self.model.controller_mode

    async def get_infrastructure(self) -> Dict[str, Any]:
        """Get static infrastructure data (tracks, stations, towers with heatmaps)."""
        async with self.lock:
            # Get heatmap points only for operational towers
            heatmap_points = []
            for tower_id, tower in self.model.radio_towers.items():
                if tower.is_operational():
                    heatmap_points.extend(self.tower_geo_cache.get(tower_id, []))

            # Build tower metadata
            towers_data = []
            for tower_id, tower in self.model.radio_towers.items():
                towers_data.append({
                    "towerId": tower_id,
                    "positionKm": tower.position_km,
                    "radiusKm": tower.radius_km,
                    "heatmapPoints": self.tower_geo_cache.get(tower_id, []),
                })

            # Build station data
            stations_data = []
            for node_id, coords in self.positioning.node_coords.items():
                stations_data.append({
                    "id": node_id,
                    "position": coords,
                    "name": node_id,
                })

            return {
                "trackPaths": self.positioning.track_paths,
                "stations": stations_data,
                "towers": towers_data,
                "viewState": {
                    "latitude": 61.4978,
                    "longitude": 22.8000,
                    "zoom": 8.2,
                    "pitch": 0,
                },
            }

    async def get_tick_snapshot(self) -> Dict[str, Any]:
        """Get current tick snapshot with all train positions."""
        async with self.lock:
            positions = self.positioning.compute_raw_positions(self.model)

            trains = []
            for agent in self.model.agents:
                status = agent.get_status()
                train_id = status["train_id"]
                position = positions.get(train_id)

                if position:
                    route_progress = "N/A"
                    try:
                        edge_index = status.get("edge_index", 0)
                        route = status.get("route", [])
                        if route:
                            route_length = len(route) - 1
                            route_progress = f"{edge_index} / {route_length}"
                    except (KeyError, TypeError, IndexError):
                        pass

                    trains.append({
                        "trainId": train_id,
                        "trainType": status.get("train_type", "passenger"),
                        "state": agent.state.value,
                        "position": position,
                        "speedKmh": float(status.get("speed_kmh", 0.0)),
                        "waitTime": status.get("wait_time", 0),
                        "currentNode": status.get("current_node"),
                        "nextNode": status.get("next_node"),
                        "routeProgress": route_progress,
                        "powerW": float(status.get("power_w", 0.0)),
                        "energyConsumedKwh": float(
                            status.get("energy_consumed_kwh", 0.0)
                        ),
                        "energyRegeneratedKwh": float(
                            status.get("energy_regenerated_kwh", 0.0)
                        ),
                        "netEnergyKwh": float(status.get("net_energy_kwh", 0.0)),
                        "accelerationMs2": float(
                            status.get("current_acceleration_ms2", 0.0)
                        ),
                        "distanceTraveledKm": float(
                            status.get("distance_traveled_km", 0.0)
                        ),
                        "controllerAction": status.get("controller_action", "CRUISE"),
                        "controllerReason": status.get("controller_reason", ""),
                        "estimatedSavingKwh": float(
                            status.get("estimated_saving_kwh", 0.0)
                        ),
                    })

            return {
                "type": "tick",
                "tick": self.tick,
                "simTime": self.tick,
                "serverTimestampMs": int(time.time() * 1000),
                "trains": trains,
                "metrics": {
                    **self.model.get_energy_metrics(),
                    "controllerMode": self.model.controller_mode,
                },
            }

    async def fail_switch(self, station_id: str, switch_index: Optional[int]):
        """Fail one or all switches at a station."""
        async with self.lock:
            if switch_index is None:
                self.model.fail_station_switches(station_id)
            else:
                self.model.fail_switch(station_id, switch_index)

    async def repair_switch(self, station_id: str, switch_index: Optional[int]):
        """Repair one or all switches at a station."""
        async with self.lock:
            if switch_index is None:
                self.model.repair_station_switches(station_id)
            else:
                self.model.repair_switch(station_id, switch_index)

    async def clamp_switch(self, station_id: str, switch_index: Optional[int], position: str):
        """Clamp one or all switches at a station to a position."""
        async with self.lock:
            if switch_index is None:
                switches = self.model.get_switches(station_id)
                for i in range(len(switches)):
                    self.model.clamp_switch(station_id, i, position)
            else:
                self.model.clamp_switch(station_id, switch_index, position)

    async def release_switch_clamp(self, station_id: str, switch_index: Optional[int]):
        """Release clamp on one or all switches at a station."""
        async with self.lock:
            if switch_index is None:
                switches = self.model.get_switches(station_id)
                for i in range(len(switches)):
                    self.model.release_switch_clamp(station_id, i)
            else:
                self.model.release_switch_clamp(station_id, switch_index)

    async def fail_radio_tower(self, tower_id: str):
        """Fail a radio tower."""
        async with self.lock:
            self.model.fail_radio_tower(tower_id)

    async def repair_radio_tower(self, tower_id: str):
        """Repair a radio tower."""
        async with self.lock:
            self.model.repair_radio_tower(tower_id)

    async def unblock_edge(self, edge_key: str):
        """Unblock a blocked edge."""
        async with self.lock:
            self.model.unblock_edge(edge_key)

    async def clear_dispatch_hold(self, target_id: str):
        """Clear a dispatch hold."""
        async with self.lock:
            self.model.clear_dispatch_hold(target_id)
