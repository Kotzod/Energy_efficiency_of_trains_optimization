"""
Positioning functions ported from Streamlit main.py
Handles train position computation, interpolation, and fallback logic.
"""

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


KM_PER_DEG_LAT = 111.0
HEATMAP_STEPS = 14


class PositioningEngine:
    """Handles all geometric calculations for train positioning and tower coverage."""

    def __init__(self, repo_root: Path):
        """
        Initialize the positioning engine with infrastructure data.

        Args:
            repo_root: Path to the repository root containing infrastructure JSON files
        """
        self.repo_root = Path(repo_root)
        self.node_coords: Dict[str, List[float]] = {}
        self.track_paths: List[Dict[str, Any]] = []
        self.nodes_by_km: List[Tuple[float, float, float]] = []
        self.edge_geometry_lookup: Dict[Tuple[str, str], List[List[float]]] = {}

        self._load_infrastructure()

    def _load_infrastructure(self):
        """Load and parse nodes_and_edges.json to build coordinate lookups."""
        json_path = self.repo_root / "infrastructure" / "nodes_and_edges.json"

        with open(json_path, encoding="utf-8") as f:
            infrastructure_data = json.load(f)

        # Build node coordinates from edges
        for edge in infrastructure_data.get("edges", []):
            geometry = edge.get("geometry", [])
            if not geometry:
                continue

            # Convert from [lat, lon] to [lon, lat]
            path = [[pt[1], pt[0]] for pt in geometry]
            self.track_paths.append({
                "path": path,
                "edgeKey": f"{edge['from']}-{edge['to']}",
            })

            from_node = edge["from"]
            to_node = edge["to"]
            if from_node not in self.node_coords:
                self.node_coords[from_node] = path[0]
            if to_node not in self.node_coords:
                self.node_coords[to_node] = path[-1]

            # Store geometry for interpolation
            self.edge_geometry_lookup[(from_node, to_node)] = geometry

        # Build node coordinates from node definitions
        for node in infrastructure_data.get("nodes", []):
            node_id = node["id"]
            if node_id not in self.node_coords:
                if "lon" in node and "lat" in node:
                    self.node_coords[node_id] = [node["lon"], node["lat"]]
                elif "geometry" in node:
                    self.node_coords[node_id] = [node["geometry"][1], node["geometry"][0]]

        # Build km-sorted node list for fallback positioning
        for node in infrastructure_data.get("nodes", []):
            km = node.get("km", 0.0)
            if "pos" in node:
                lat, lon = node["pos"]
            elif "geometry" in node:
                lat, lon = node["geometry"][0], node["geometry"][1]
            else:
                lat = node.get("lat")
                lon = node.get("lon")

            if lat is not None and lon is not None:
                self.nodes_by_km.append((km, lat, lon))

        self.nodes_by_km.sort(key=lambda x: x[0])

    def km_to_latlon(self, position_km: float) -> Tuple[Optional[float], Optional[float]]:
        """
        Map absolute position (km) to lat/lon coordinates using km-sorted nodes.

        Args:
            position_km: Absolute position in kilometers

        Returns:
            Tuple of (lat, lon) or (None, None) if not found
        """
        if not self.nodes_by_km:
            return None, None

        if position_km <= self.nodes_by_km[0][0]:
            return self.nodes_by_km[0][1], self.nodes_by_km[0][2]

        if position_km >= self.nodes_by_km[-1][0]:
            return self.nodes_by_km[-1][1], self.nodes_by_km[-1][2]

        for i in range(len(self.nodes_by_km) - 1):
            km1, lat1, lon1 = self.nodes_by_km[i]
            km2, lat2, lon2 = self.nodes_by_km[i + 1]
            if km1 <= position_km <= km2:
                t = (position_km - km1) / (km2 - km1) if (km2 - km1) != 0 else 0
                lat = lat1 + t * (lat2 - lat1)
                lon = lon1 + t * (lon2 - lon1)
                return lat, lon

        return None, None

    def interpolate_train_position(
        self,
        from_node: str,
        to_node: str,
        progress: float,
        edge_geometry: Optional[List[List[float]]] = None,
    ) -> Optional[List[float]]:
        """
        Interpolate train position along a path using multi-point edge geometry.

        Args:
            from_node: Starting node ID
            to_node: Ending node ID
            progress: Progress fraction [0, 1]
            edge_geometry: Optional edge geometry from JSON

        Returns:
            [lon, lat] position or None
        """
        if edge_geometry:
            # Convert from [lat, lon] to [lon, lat]
            path = [[pt[1], pt[0]] for pt in edge_geometry]
        elif from_node in self.node_coords and to_node in self.node_coords:
            path = [self.node_coords[from_node], self.node_coords[to_node]]
        else:
            return self.node_coords.get(from_node) or self.node_coords.get(to_node)

        if progress <= 0:
            return path[0]
        if progress >= 1:
            return path[-1]

        # Compute segment distances
        segment_distances = []
        for i in range(len(path) - 1):
            p1, p2 = path[i], path[i + 1]
            segment_distances.append(np.hypot(p2[0] - p1[0], p2[1] - p1[1]))

        total_distance = sum(segment_distances)
        if total_distance == 0:
            return path[0]

        target_distance = progress * total_distance
        accumulated_distance = 0

        for i in range(len(path) - 1):
            p1, p2 = path[i], path[i + 1]
            dist = segment_distances[i]
            if accumulated_distance + dist >= target_distance:
                segment_progress = (target_distance - accumulated_distance) / dist if dist > 0 else 0
                return [
                    p1[0] + (p2[0] - p1[0]) * segment_progress,
                    p1[1] + (p2[1] - p1[1]) * segment_progress,
                ]
            accumulated_distance += dist

        return path[-1]

    def compute_raw_positions(self, model) -> Dict[str, List[float]]:
        """
        Compute current position for all trains in the model.

        Uses priority: current_edge geometry -> current_node -> km fallback

        Args:
            model: RailwayModel instance

        Returns:
            Dict mapping train_id -> [lon, lat]
        """
        positions = {}

        for agent in model.agents:
            status = agent.get_status()
            pos = None

            # Try current edge with geometry
            if status.get("current_edge") is not None:
                u, v = status["current_edge"]
                geom = self.edge_geometry_lookup.get((u, v)) or self.edge_geometry_lookup.get((v, u))
                pos = self.interpolate_train_position(u, v, status.get("progress", 0.0), geom)

            # Try current node
            if pos is None:
                curr_node = status.get("current_node")
                if curr_node in self.node_coords:
                    pos = self.node_coords[curr_node]

            # Try absolute km fallback
            if pos is None:
                abs_position_km = status.get("abs_position_km")
                if abs_position_km is not None:
                    lat, lon = self.km_to_latlon(abs_position_km)
                    if lat is not None and lon is not None:
                        pos = [lon, lat]

            if pos:
                positions[status["train_id"]] = pos

        return positions

    def build_tower_geo_points(self, tower) -> List[Dict[str, Any]]:
        """
        Generate heatmap point cloud for a radio tower.

        Uses tower.strength_at_distance() to weight each point.
        This is computed once per tower and cached.

        Args:
            tower: RadioTower instance

        Returns:
            List of {"position": [lon, lat], "weight": float}
        """
        lat, lon = self.km_to_latlon(tower.position_km)
        if lat is None or lon is None:
            return []

        radius_deg_lat = tower.radius_km / KM_PER_DEG_LAT
        radius_deg_lon = radius_deg_lat / math.cos(math.radians(lat))

        points = []
        for i in range(-HEATMAP_STEPS, HEATMAP_STEPS + 1):
            for j in range(-HEATMAP_STEPS, HEATMAP_STEPS + 1):
                dlat = i * radius_deg_lat / HEATMAP_STEPS
                dlon = j * radius_deg_lon / HEATMAP_STEPS

                dist_km = math.sqrt(
                    (dlat * KM_PER_DEG_LAT) ** 2
                    + (dlon * KM_PER_DEG_LAT * math.cos(math.radians(lat))) ** 2
                )

                if dist_km <= tower.radius_km:
                    points.append({
                        "position": [lon + dlon, lat + dlat],
                        "weight": tower.strength_at_distance(dist_km),
                    })

        return points


def lerp_position(p_from: List[float], p_to: List[float], t: float) -> List[float]:
    """
    Linear interpolation between two positions.

    Args:
        p_from: [lon, lat] starting position
        p_to: [lon, lat] ending position
        t: Interpolation factor [0, 1]

    Returns:
        Interpolated [lon, lat]
    """
    t = max(0.0, min(1.0, t))
    return [
        p_from[0] + (p_to[0] - p_from[0]) * t,
        p_from[1] + (p_to[1] - p_from[1]) * t,
    ]
