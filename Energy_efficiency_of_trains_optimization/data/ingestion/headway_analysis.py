"""
Headway Analysis Module
Tampere–Pori/Rauma Corridor (ABM Thesis Pipeline)

Computes consecutive train headways between stations as a proxy for
block signaling intervals (suojastusvälit).
"""

import pandas as pd

FREIGHT_OPS = {"vrc", "ferfi", "operail", "winco"}

# ---------------------------------------------------------------------------
# Part 2 — Headway analysis (block signaling proxy)
# ---------------------------------------------------------------------------

def compute_headways(df: pd.DataFrame, from_station: str, to_station: str,
                     direction_label: str) -> pd.DataFrame:
    """
    Computes consecutive train headways between two stations.
    A large minimum headway confirms long suojastusvälit (block spacing).
    """
    dep = df[(df["stationCode"] == from_station) & (df["rowType"] == "DEPARTURE")].copy()
    arr = df[(df["stationCode"] == to_station)   & (df["rowType"] == "ARRIVAL")].copy()

    dep["actual"] = pd.to_datetime(dep["actual"], errors="coerce", utc=True)
    arr["actual"] = pd.to_datetime(arr["actual"], errors="coerce", utc=True)

    seg = pd.merge(
        dep[["trainNumber", "departureDate", "actual", "is_freight"]],
        arr[["trainNumber", "departureDate", "actual"]],
        on=["trainNumber", "departureDate"],
        suffixes=("_dep", "_arr"),
    )
    seg = seg[seg["actual_dep"] < seg["actual_arr"]].sort_values("actual_dep")
    seg["transit_min"] = (seg["actual_arr"] - seg["actual_dep"]).dt.total_seconds() / 60.0
    seg["headway_min"] = seg["actual_dep"].diff().dt.total_seconds() / 60.0

    seg = seg[(seg["headway_min"] > 0) & (seg["headway_min"] < 180)].copy()
    seg["direction"] = direction_label
    return seg