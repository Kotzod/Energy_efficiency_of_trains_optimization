import json
import os
from typing import Dict, List

import networkx as nx

from .node import Node
from .edge import TrackEdge
from .switch import Switch


def build_graph() -> nx.MultiGraph:
    base      = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base, "nodes_and_edges.json")

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    graph = nx.MultiGraph()

    node_objects: Dict[str, Node]         = {}
    switches:     Dict[str, List[Switch]] = {}

    # ── Nodes ──────────────────────────────────────────────────────────────────
    for node_data in data["nodes"]:
        node = Node(
            node_id          = node_data["id"],
            name             = node_data["name"],
            km               = node_data["km"],
            passing_loop     = node_data["passing_loop"],
            passenger_stop   = node_data["passenger_stop"],
            max_train_length = node_data.get("max_train_length"),
        )
        node_objects[node.id] = node

        graph.add_node(
            node.id,
            name             = node.name,
            km               = node.km,
            pos              = node_data.get("pos", [0, 0]),
            passenger_stop   = node.passenger_stop,
            passing_loop     = node.passing_loop,
            station_capacity = node_data.get("station_capacity", 0),
            yard_capacity    = node_data.get("yard_capacity", 0),
            switch_count     = node_data.get("switch_count", 0),
            criticality      = node_data.get("criticality", "LOW"),
            node_object      = node,
        )

        switch_count = node_data.get("switch_count", 0)
        if switch_count > 0:
            roles = _allocate_switch_roles(node_data)
            switches[node.id] = [
                Switch(switch_id=f"{node.id}_SW_{i+1}", station_id=node.id, role=role)
                for i, role in enumerate(roles)
            ]

    # ── Edges ──────────────────────────────────────────────────────────────────
    node_km = {n["id"]: n["km"] for n in data["nodes"]}

    for edge_data in data["edges"]:
        from_id     = edge_data["from"]
        to_id       = edge_data["to"]
        distance_km = abs(node_km[to_id] - node_km[from_id])
        tracks      = edge_data["tracks"]
        gradient = edge_data.get("gradient", 0.0)
        speed_limit_kmh = edge_data.get("speed_limit_kmh", 140.0)

        if tracks > 1:
            # Double track: shared TrackEdge, two directed graph edges
            edge = TrackEdge(
                from_node=from_id, to_node=to_id,
                distance_km=distance_km, tracks=tracks,
                gradient=gradient, speed_limit_kmh=speed_limit_kmh,
            )
            graph.add_edge(from_id, to_id, key="Track_1",
                direction="Westbound", track_edge=edge)
            graph.add_edge(to_id, from_id, key="Track_2",
                direction="Eastbound", track_edge=edge)
        else:
            # Single track: two separate TrackEdge objects linked as opposites
            edge_ab = TrackEdge(
                from_node=from_id, to_node=to_id,
                distance_km=distance_km, tracks=1,
                gradient=gradient, speed_limit_kmh=speed_limit_kmh,
            )
            edge_ba = TrackEdge(
                from_node=to_id, to_node=from_id,
                distance_km=distance_km, tracks=1,
                gradient=-gradient, speed_limit_kmh=speed_limit_kmh,
            )
            edge_ab.opposite = edge_ba
            edge_ba.opposite = edge_ab

            graph.add_edge(from_id, to_id, key="Single_Track_AB",
                direction="AB", track_edge=edge_ab)
            graph.add_edge(to_id, from_id, key="Single_Track_BA",
                direction="BA", track_edge=edge_ba)

    graph.graph['switches'] = switches
    return graph

def _allocate_switch_roles(node_data: dict) -> List[str]:
    """
    Determine what each switch at a station is used for, based on the
    station's known characteristics. Real switch counts scale with a
    station's function: bigger yards need more yard-access switches,
    stations with passing loops need dedicated entry/exit switches,
    and everything else serves the through line.
    """
    switch_count = node_data.get("switch_count", 0)
    if switch_count == 0:
        return []

    passing_loop     = node_data.get("passing_loop", False)
    yard_capacity     = node_data.get("yard_capacity", 0)
    station_capacity  = node_data.get("station_capacity", 0)

    roles = ["through"]  # every station needs at least one main-line switch
    remaining = switch_count - 1

    if passing_loop and remaining >= 2:
        roles.extend(["loop_entry", "loop_exit"])
        remaining -= 2

    if remaining > 0:
        total_capacity = yard_capacity + station_capacity
        yard_share = (yard_capacity / total_capacity) if total_capacity > 0 else 0.5

        yard_switches = min(round(remaining * yard_share), remaining)
        roles.extend(["yard"] * yard_switches)
        roles.extend(["through"] * (remaining - yard_switches))

    return roles