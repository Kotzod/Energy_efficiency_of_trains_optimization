"""
Track Constraint Validator - Master Runner
Tampere–Pori/Rauma Corridor (ABM Thesis Pipeline)

Main entry point that orchestrates the validation of WSP Development Plan
track-level constraints against empirical Digitraffic timetable data.

This module imports from:
  - compositions: API enrichment functions
  - headway_analysis: Headway computation
  - validators: Constraint validation functions

Usage:
    from track_constraint_validator import run_all_validations
    run_all_validations(df, enrich_with_compositions=True)
"""

from pathlib import Path

import pandas as pd

from compositions import fetch_compositions_for_dates, enrich_timetable
from validators import (
    validate_block_signaling,
    validate_loop_length,
    validate_axle_load_corridor,
    validate_tahkoluoto_single_slot,
    validate_riihimaki_cascade,
    validate_harjavalta_industrial_spillover,
)

FREIGHT_OPS = {"vrc", "ferfi", "operail", "winco"}


# ---------------------------------------------------------------------------
# Part 4 — Master runner
# ---------------------------------------------------------------------------

def run_all_validations(df: pd.DataFrame,
                        enrich_with_compositions: bool = False,
                        compositions_cache: Path = None):
    """
    Main entry point. Pass the flattened + introduced_latency DataFrame
    from your existing data_validator_for_correlation script.

    Example:
        from track_constraint_validator import run_all_validations
        run_all_validations(df, enrich_with_compositions=True,
                            compositions_cache=Path("data/raw/compositions_cache.parquet"))
    """
    # Ensure helper columns exist
    if "is_freight" not in df.columns:
        df = df.copy()
        df["is_freight"] = df["operatorCode"].str.lower().isin(FREIGHT_OPS)

    if "introduced_latency" not in df.columns:
        df["introduced_latency"] = df["delayMinutes"].clip(lower=0)

    if enrich_with_compositions:
        comp_df = fetch_compositions_for_dates(
            df["departureDate"].unique(),
            cache_path=compositions_cache,
        )
        if not comp_df.empty:
            df = enrich_timetable(df, comp_df)
            print(f"Enriched with compositions: {len(comp_df)} records merged.")
        else:
            print("Warning: compositions fetch returned empty — running in proxy mode.")
            for col in ["totalLength", "wagon_count", "locomotive_count"]:
                if col not in df.columns:
                    df[col] = 0
    else:
        for col in ["totalLength", "wagon_count", "locomotive_count"]:
            if col not in df.columns:
                df[col] = 0

    print("\n" + "=" * 80)
    print("    NON-STATION TRACK CONSTRAINT VALIDATION REPORT")
    print("    Tampere–Pori/Rauma — WSP Development Plan Cross-Reference")
    print("=" * 80)

    validate_block_signaling(df)
    validate_loop_length(df)
    validate_axle_load_corridor(df)
    validate_tahkoluoto_single_slot(df)
    validate_riihimaki_cascade(df)
    validate_harjavalta_industrial_spillover(df)

    print("\n" + "=" * 80)
    print("    SIMULATION PARAMETER RECOMMENDATIONS")
    print("=" * 80)
    print("""
  Use the outputs above to set these ABM parameters directly:

  A. Block signaling  → min_block_headway_min = P10 headway per segment
                        (movement authority timeout for agent entry)

  B. Loop limit       → Node attribute: loop_max_length_m = 700
                        TrainAgent.length > 700 triggers bypass routing

  C. Axle load        → if wagon_count exceeds 22.5t capacity on KKI–POV:
                        force multi-locomotive flag (speed penalty applied)

  D. TAH single slot  → Node('TAH').slot_capacity = 1
                        arrival conflict → queue agent, add conflict_latency_premium

  E. TPE cascade      → multiply downstream delay probability by cascade_multiplier
                        for agents departing TPE with tpe_delay > 5 min

  F. HVA shunting     → increase HVA delay probability by 1.5x during 06:00–18:00
                        for freight agents (industrial shift overlap)
""")