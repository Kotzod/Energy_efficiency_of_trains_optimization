import json
from datetime import datetime, timedelta
from pathlib import Path

import requests

GRAPHQL_URL  = "https://rata.digitraffic.fi/api/v2/graphql/graphql"
REST_BASE    = "https://rata.digitraffic.fi/api/v1"
HEADERS = {
    "Content-Type": "application/json",
    "Accept-Encoding": "gzip",
    "User-Agent": "AcademicThesiSimulation/1.0 (Tampere University of Applied Sciences)"
}

# ============================================================
# CHANGE THESE BETWEEN RUNS:
#
# RUN 1:  START = "2025-11-01"  END = "2025-12-26"  NAME = "digitraffic_corridor_winter_run1"
# RUN 2:  START = "2025-12-27"  END = "2026-02-23"  NAME = "digitraffic_corridor_winter_run2"
# RUN 3:  START = "2026-02-21"  END = "2026-04-18"  NAME = "digitraffic_corridor_winter_run3"
# ============================================================
STUDY_START_DATE = "2025-11-01"
STUDY_END_DATE   = "2025-12-27"
OUTPUT_BASENAME  = "digitraffic_track_validator"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
COMBINED_OUTPUT_PATH = RAW_DATA_DIR / f"{OUTPUT_BASENAME}.json"

CORRIDOR_STATION_CODES = ["TPE", "LLH", "NOK", "KKI", "HVA", "PRI", "POV", "TAH", "TLU"]
FREIGHT_OPS = {"vrc", "ferfi", "operail", "winco"}


def parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


# ── GraphQL: timetable rows ────────────────────────────────────────────

def build_query(date_str):
    station_filters = ",\n          ".join(
        '{ timeTableRows: { contains: { station: { shortCode: { equals: "%s" } } } } }' % code
        for code in CORRIDOR_STATION_CODES
    )
    return """
    {
      trainsByDepartureDate(departureDate: "%s", where: {
        or: [
          %s
        ]
      }) {
        trainNumber
        departureDate
        operator {
          shortCode
        }
        timeTableRows {
          station {
            shortCode
          }
          type
          scheduledTime
          actualTime
          differenceInMinutes
          trainStopping
          commercialStop
        }
      }
    }
    """ % (date_str, station_filters)


def fetch_timetable_day(date_value):
    date_str = date_value.strftime("%Y-%m-%d")
    print(f"  [GraphQL] timetable {date_str}...")
    try:
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": build_query(date_str)},
            headers=HEADERS,
            timeout=60
        )
        if resp.status_code != 200:
            print(f"    HTTP {resp.status_code} — skipping")
            return []
        data = resp.json()
        if "errors" in data:
            print(f"    GraphQL errors: {data['errors']}")
            return []
        return data.get("data", {}).get("trainsByDepartureDate", [])
    except Exception as exc:
        print(f"    Error: {exc}")
        return []


# ── REST: compositions ─────────────────────────────────────────────────

def fetch_compositions_day(date_value):
    """
    GET /api/v1/compositions/{date}
    Returns dict keyed by trainNumber -> {totalLength, maximumSpeed,
    locomotive_count, wagon_count, max_weightPerAxle}
    """
    date_str = date_value.strftime("%Y-%m-%d")
    print(f"  [REST]    compositions {date_str}...")
    try:
        resp = requests.get(
            f"{REST_BASE}/compositions/{date_str}",
            headers={k: v for k, v in HEADERS.items() if k != "Content-Type"},
            timeout=60
        )
        if resp.status_code != 200:
            print(f"    HTTP {resp.status_code} — skipping")
            return {}
        result = {}
        for train in resp.json():
            number   = train.get("trainNumber")
            sections = train.get("journeySections") or []
            loco_count  = 0
            wagon_count = 0
            max_wpa     = 0.0
            total_len   = 0
            for sec in sections:
                loco_count += len(sec.get("locomotives") or [])
                for wagon in (sec.get("wagons") or []):
                    wagon_count += 1
                    wpa = wagon.get("weightPerAxle") or 0
                    if wpa > max_wpa:
                        max_wpa = wpa
                    total_len += wagon.get("length") or 0
            result[number] = {
                "totalLength":       train.get("totalLength") or total_len,
                "maximumSpeed":      train.get("maximumSpeed") or 0,
                "locomotive_count":  loco_count,
                "wagon_count":       wagon_count,
                "max_weightPerAxle": max_wpa,
            }
        return result
    except Exception as exc:
        print(f"    Error: {exc}")
        return {}


# ── Merge and flatten ──────────────────────────────────────────────────

def flatten_and_merge(trains, comp_map):
    """
    One record per timetable row, composition fields joined by trainNumber.

    Field → validator mapping:
        trainNumber, departureDate       — join key (all)
        operatorCode, is_freight         — B (loop bypass), F (day-shift)
        totalLength                      — B (consist > 700m?)
        maximumSpeed                     — B
        locomotive_count, wagon_count    — B, C
        max_weightPerAxle                — C (exceeds 22.5t on KKI–POV?)
        stationCode, type                — A (DEPARTURE rows for headway gaps)
        scheduledTime, actualTime        — A, D (TAH slot window)
        differenceInMinutes              — C, E (cascade multiplier), F (HVA day/night)
        trainStopping, commercialStop    — B (loop station stop vs bypass)
    """
    records = []
    for train in trains:
        number         = train.get("trainNumber")
        departure_date = train.get("departureDate")
        operator_code  = (train.get("operator") or {}).get("shortCode", "")
        is_freight     = operator_code.lower() in FREIGHT_OPS

        comp = comp_map.get(number, {})
        total_length     = comp.get("totalLength", 0)
        maximum_speed    = comp.get("maximumSpeed", 0)
        locomotive_count = comp.get("locomotive_count", 0)
        wagon_count      = comp.get("wagon_count", 0)
        max_wpa          = comp.get("max_weightPerAxle", 0.0)

        for row in (train.get("timeTableRows") or []):
            records.append({
                "trainNumber":         number,
                "departureDate":       departure_date,
                "operatorCode":        operator_code,
                "is_freight":          is_freight,
                "totalLength":         total_length,
                "maximumSpeed":        maximum_speed,
                "locomotive_count":    locomotive_count,
                "wagon_count":         wagon_count,
                "max_weightPerAxle":   max_wpa,
                "stationCode":         (row.get("station") or {}).get("shortCode"),
                "type":                row.get("type"),
                "scheduledTime":       row.get("scheduledTime"),
                "actualTime":          row.get("actualTime"),
                "differenceInMinutes": row.get("differenceInMinutes"),
                "trainStopping":       row.get("trainStopping"),
                "commercialStop":      row.get("commercialStop"),
            })
    return records


# ── Main loop ──────────────────────────────────────────────────────────

def fetch_all(start_date, end_date):
    all_records = []
    current = start_date
    while current <= end_date:
        trains   = fetch_timetable_day(current)
        comp_map = fetch_compositions_day(current)
        records  = flatten_and_merge(trains, comp_map)
        all_records.extend(records)
        print(f"    → {len(records)} rows")
        current += timedelta(days=1)
    return all_records


def save_json(path, data):
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Saved {len(data)} rows to: {path}")


def main():
    study_start = parse_date(STUDY_START_DATE)
    study_end   = parse_date(STUDY_END_DATE)

    print("\n" + "=" * 80)
    print(f"Fetching Digitraffic data: {study_start:%Y-%m-%d} to {study_end:%Y-%m-%d}")
    print(f"Output: {COMBINED_OUTPUT_PATH}")
    print("=" * 80)

    records = fetch_all(study_start, study_end)
    save_json(COMBINED_OUTPUT_PATH, records)
    print(f"Done. Total rows: {len(records)}")


if __name__ == "__main__":
    main()