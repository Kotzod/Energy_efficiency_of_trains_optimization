import json
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "raw" / "digitraffic_corridor_winter.json"

PASSENGER_OPERATORS = {"vr", "hmvy"}
FREIGHT_OPERATORS = {"vrc", "ferfi", "operail", "winco"}
SERVICE_OPERATORS = {"destia", "sweco-ir", "sundstroms", "vr-track"}


def _text_value(value):
    if isinstance(value, dict):
        return " ".join(str(item) for item in value.values() if item is not None)
    if isinstance(value, list):
        return " ".join(_text_value(item) for item in value)
    return "" if value is None else str(value)


def classify_traffic_profile(train):
    """Classify train traffic using Digitraffic fields, then robust fallbacks.

    The current JSON export does not include trainCategory/trainType. If future
    exports include those fields, they are used first. Otherwise, the fallback
    uses operator code, commuter line id, and train-number bands observed in the
    Tampere-Pori/Rauma corridor extract.
    """
    operator_block = train.get("operator") or {}
    operator_code = str(operator_block.get("shortCode") or "UNKNOWN").strip().lower()
    commuter_line = train.get("commuterLineid") or train.get("commuterLineID")
    train_number = train.get("trainNumber")

    category_text = " ".join(
        _text_value(train.get(field))
        for field in ("trainCategory", "category", "trainType", "type")
    ).lower()

    if any(token in category_text for token in ("cargo", "freight", "goods", "tavara")):
        return "Freight/Cargo", 1
    if any(token in category_text for token in ("passenger", "commuter", "long-distance", "henkilo")):
        return "Passenger", 0
    if any(token in category_text for token in ("maintenance", "service", "work")):
        return "Service/Other", 0

    if operator_code in FREIGHT_OPERATORS:
        return "Freight/Cargo", 1
    if operator_code in SERVICE_OPERATORS:
        return "Service/Other", 0
    if commuter_line not in (None, ""):
        return "Passenger", 0

    try:
        number = int(train_number)
    except (TypeError, ValueError):
        number = None

    if number is not None:
        if number < 1000:
            return "Passenger", 0
        if 2000 <= number <= 5999 or number >= 50000:
            return "Freight/Cargo", 1

    if operator_code in PASSENGER_OPERATORS:
        return "Passenger", 0
    return "Unknown", 0


def correlation_label(node_rows):
    if node_rows.empty:
        return "NOT OBSERVABLE"

    failure_probability = (node_rows["introduced_latency"].gt(0).sum() / len(node_rows)) * 100
    mean_latency = node_rows["introduced_latency"].mean()
    tech_stops = ((node_rows["trainStopping"] == True) & (node_rows["commercialStop"] == False)).sum()
    has_freight = node_rows["trafficProfile"].eq("Freight/Cargo").any()
    profile_signal = node_rows.groupby("trafficProfile")["introduced_latency"].agg(
        mean_latency="mean",
        failure_probability=lambda x: x.gt(0).mean() * 100
    )

    if (
        failure_probability >= 15
        or mean_latency >= 1
        or tech_stops >= 50
        or profile_signal["failure_probability"].ge(15).any()
        or profile_signal["mean_latency"].ge(1).any()
    ):
        return "SUPPORTED"
    if has_freight or failure_probability >= 5 or tech_stops > 0:
        return "PARTIALLY SUPPORTED"
    return "WEAK / LOW-SIGNAL"


def load_trains_from_json(json_filepath):
    json_path = Path(json_filepath)
    if not json_path.is_absolute():
        json_path = PROJECT_ROOT / json_path

    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # Check if data was wrapped inside standard GraphQL envelope root
    if isinstance(data, dict) and "data" in data:
        trains_list = data["data"].get("trainsByDepartureDate", [])
    elif isinstance(data, dict) and "trainsByDepartureDate" in data:
        trains_list = data["trainsByDepartureDate"]
    else:
        trains_list = data

    print(f"Loaded {len(trains_list)} trains from: {json_path}")
    return trains_list


def analyze_infrastructure_correlations(json_filepaths):
    # Step 1: Open and standardize data ingestion streams
    if isinstance(json_filepaths, (str, Path)):
        json_filepaths = [json_filepaths]

    trains_list = []
    for json_filepath in json_filepaths:
        trains_list.extend(load_trains_from_json(json_filepath))

    flattened_data = []

    # Step 2: Unpack deep timetable matrices
    for train in trains_list:
        train_id = train.get("trainNumber")
        date = train.get("departureDate")
        op_block = train.get("operator")
        op_code = op_block.get("shortCode") if op_block else "UNKNOWN"
        traffic_profile, is_freight = classify_traffic_profile(train)
        commuter_line = train.get("commuterLineid") or train.get("commuterLineID")

        timetable = train.get("timeTableRows", [])
        for idx, checkpoint in enumerate(timetable):
            st_block = checkpoint.get("station")
            if not st_block:
                continue
            st_code = st_block.get("shortCode")

            flattened_data.append({
                "trainNumber": train_id,
                "departureDate": date,
                "is_freight": is_freight,
                "trafficProfile": traffic_profile,
                "operatorCode": op_code,
                "commuterLine": commuter_line,
                "stationCode": st_code,
                "rowType": checkpoint.get("type"),
                "scheduled": checkpoint.get("scheduledTime"),
                "actual": checkpoint.get("actualTime"),
                "delayMinutes": checkpoint.get("differenceInMinutes", 0),
                "trainStopping": checkpoint.get("trainStopping", False),
                "commercialStop": checkpoint.get("commercialStop", False),
                "sequenceIndex": idx
            })

    df = pd.DataFrame(flattened_data)
    if df.empty:
        print("Data ingestion error: No valid structural elements unpacked.")
        return

    # Standardize operational delay fields
    df["delayMinutes"] = df["delayMinutes"].fillna(0).astype(int)
    df = df.sort_values(by=["trainNumber", "departureDate", "sequenceIndex"]).reset_index(drop=True)

    # Step 3: Compute Delta Delay (Disruption Generation Metric)
    # Isolates delays introduced specifically at a station or section.
    df["incoming_delay"] = df.groupby(["trainNumber", "departureDate"])["delayMinutes"].shift(1).fillna(0)
    df["delta_delay"] = df["delayMinutes"] - df["incoming_delay"]
    df["introduced_latency"] = df["delta_delay"].clip(lower=0)

    # Step 4: Map WSP documented severity targets to Digitraffic station codes.
    # Some WSP asset labels differ from Digitraffic station short codes.
    severity_targets = {
        "NOK": {
            "name": "Nokia Station Yard",
            "station_codes": ["NOK"],
            "issue": "Single-platform layout coupled with restrictive signaling paths. Causes passenger boarding delays and stalls overtaking freight corridors.",
            "expected_signal": "Passenger dwell delay, freight path conflicts, and localized delay spikes.",
            "doc_ref": "Page 7 & 26"
        },
        "KKI": {
            "name": "Kokemaki Junction",
            "station_codes": ["KKI"],
            "issue": "Strategic line splitting point between Pori passenger flows and Rauma maritime industrial lines. Prone to severe interlocking waiting delays.",
            "expected_signal": "High number of non-commercial stops and delay generation around the Pori/Rauma split.",
            "doc_ref": "Page 7 & 22"
        },
        "HVA": {
            "name": "Harjavalta Railyard",
            "station_codes": ["HVA"],
            "issue": "High industrial concentration and processing volume causing severe yard shunting congestion and main line spillover.",
            "expected_signal": "Freight-heavy exposure, technical stops, and mainline delay transfer.",
            "doc_ref": "Page 7 & 22"
        },
        "PRI": {
            "name": "Pori Railyard (Main)",
            "station_codes": ["PRI"],
            "issue": "Tracks are entirely under 700 meters long, preventing its use as a buffer yard for modern heavy freight configurations.",
            "expected_signal": "Terminal delay generation and poor buffering, especially where freight and passenger movements overlap.",
            "doc_ref": "Page 7 & 22"
        },
        "POV": {
            "name": "Tahkoluodon Ratapiha",
            "station_codes": ["POV", "TAH", "TLU"],
            "issue": "Extremely constrained sorting yard footprint. Main entry layout restricts unloading operations to a single train at a time.",
            "expected_signal": "Freight-only terminal movements and unloading-related queuing.",
            "doc_ref": "Page 7 & 16"
        },
        "LLI": {
            "name": "Lielahti Junction Area",
            "station_codes": ["LLI", "LLH"],
            "issue": "The critical funnel tracking double lines down to raw single track sections heading west from Tampere main yard.",
            "expected_signal": "Mixed-traffic funnel effects immediately west of Tampere.",
            "doc_ref": "Page 7 & 16"
        }
    }

    station_to_asset = {}
    for asset_code, meta in severity_targets.items():
        for station_code in meta["station_codes"]:
            station_to_asset[station_code] = asset_code

    df_targeted = df[df["stationCode"].isin(station_to_asset.keys())].copy()
    df_targeted["assetCode"] = df_targeted["stationCode"].map(station_to_asset)

    print("\n" + "=" * 80)
    print("      INFRASTRUCTURE CONSTRAINT CORRELATION REPORT (DIGITRAFFIC VS. WSP PLAN)")
    print("=" * 80)
    print("\nTraffic profile coverage in parsed timetable rows:")
    for profile, count in df["trafficProfile"].value_counts().items():
        print(f"  - {profile}: {count} timetable rows")

    # Analyze vulnerabilities node-by-node
    for code, meta in severity_targets.items():
        sub_node = df_targeted[df_targeted["assetCode"] == code]
        observed_codes = ", ".join(sorted(sub_node["stationCode"].unique())) if not sub_node.empty else "none"

        print(f"\nTarget Asset: {meta['name']} ({code})")
        print(f"Digitraffic Station Codes Checked: {', '.join(meta['station_codes'])} | Observed: {observed_codes}")
        print(f"Documented Constraint: {meta['issue']} [Doc Ref: {meta['doc_ref']}]")
        print(f"Expected Digitraffic Signal: {meta['expected_signal']}")

        if sub_node.empty:
            print("  --> [CORRELATION: NOT OBSERVABLE] No active traffic entries encountered in dataset for this node.")
            print("      Check the upstream Digitraffic query: freight-only branches may not pass the current TPE filter.")
            continue

        print(f"  --> [CORRELATION: {correlation_label(sub_node)}]")

        # Calculate distinct statistical variances for cargo vs. passenger lines
        metrics = sub_node.groupby("trafficProfile").agg(
            avg_lat=("introduced_latency", "mean"),
            peak_lat=("introduced_latency", "max"),
            total_events=("introduced_latency", "count"),
            unique_trains=("trainNumber", "nunique"),
            delay_incidents=("introduced_latency", lambda x: (x > 0).sum()),
            tech_stops=("trainStopping", lambda x: ((x == True) & (sub_node.loc[x.index, "commercialStop"] == False)).sum())
        ).reset_index().sort_values(by="avg_lat", ascending=False)

        for _, row in metrics.iterrows():
            pct_disrupted = (row["delay_incidents"] / row["total_events"]) * 100 if row["total_events"] > 0 else 0

            print(f"  * Traffic Profile: {row['trafficProfile']}")
            print(f"    - Mean Delay Generated At Node: {row['avg_lat']:.2f} minutes")
            print(f"    - Maximum Disruption Spike:     {row['peak_lat']} minutes")
            print(f"    - Node Vulnerability Ratio:     {pct_disrupted:.1f}% of timetable rows delayed at this point")
            print(f"    - Unique Trains Observed:       {int(row['unique_trains'])}")
            print(f"    - Enforced Signaling/Tech Stops: {int(row['tech_stops'])} occurrences")

        print("-" * 60)

    # Compute overall corridor vulnerability rankings for your thesis environment
    print("\n" + "=" * 80)
    print("                   CRITICALITY RANKING FOR SIMULATION VALIDATION")
    print("=" * 80)

    vulnerability_matrix = df_targeted.groupby("assetCode").agg(
        gross_minutes=("introduced_latency", "sum"),
        check_count=("introduced_latency", "count"),
        strike_count=("introduced_latency", lambda x: (x > 0).sum()),
        passenger_rows=("trafficProfile", lambda x: (x == "Passenger").sum()),
        freight_rows=("trafficProfile", lambda x: (x == "Freight/Cargo").sum())
    ).reset_index()

    vulnerability_matrix["failure_probability"] = (
        vulnerability_matrix["strike_count"] / vulnerability_matrix["check_count"]
    ) * 100
    vulnerability_matrix = vulnerability_matrix.sort_values(by="gross_minutes", ascending=False)

    for rank, (_, row) in enumerate(vulnerability_matrix.iterrows(), 1):
        asset_name = severity_targets[row["assetCode"]]["name"]
        print(f"Rank {rank}: {asset_name} ({row['assetCode']})")
        print(f"        - Impact: Contributed {int(row['gross_minutes'])} total delay minutes across the corridor window.")
        print(f"        - Disruption Risk: {row['failure_probability']:.1f}% chance of generating delay per timetable row.")
        print(f"        - Profile Mix: {int(row['passenger_rows'])} passenger rows, {int(row['freight_rows'])} freight/cargo rows.")


# Execute pipeline on target source file
if __name__ == "__main__":
    input_paths = sys.argv[1:] if len(sys.argv) > 1 else [DEFAULT_DATA_PATH]
    analyze_infrastructure_correlations(input_paths)
