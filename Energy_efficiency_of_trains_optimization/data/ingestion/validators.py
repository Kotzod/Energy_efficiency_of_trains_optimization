"""
Track Constraint Validators Module
Tampere–Pori/Rauma Corridor (ABM Thesis Pipeline)

Validates WSP Development Plan track-level constraints against
empirical Digitraffic timetable data.

Constraints validated (from WSP PDF, Page 7, 16 & 22):
  A. Block signaling intervals  — long suojastusvälit between Tampere and Pori
  B. Passing loop length limit  — no loops handle >700m; freight standard is 750m
  C. Axle load 22.5t cap        — Kokemäki–Tahkoluoto section
  D. Tahkoluoto single-slot     — one train unloaded at a time (cascades upstream)
  E. Riihimäki–Tampere cascade  — upstream congestion disrupts Tahkoluoto scheduling
  F. Harjavalta industrial ops  — shunting volume causes mainline spillover
  G. Electrification dividend   — wagon count increase 40→48 Harjavalta–Mäntyluoto
"""

import pandas as pd

from headway_analysis import compute_headways

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

FREIGHT_STANDARD_LENGTH_M = 750
LOOP_DESIGN_LIMIT_M       = 700
AXLE_LIMIT_CORRIDOR       = 22.5

PASSING_LOOP_STATIONS = ["SNI", "TRV", "AHV", "KRK", "SRO", "KUK"]
KKI_TO_POV_STATIONS   = ["KKI", "HVA", "PRI", "POV"]
TPE_TO_PRI_ORDERED    = ["TPE", "LLH", "NOK", "KRK", "SRO", "AHV", "KKI", "HVA", "PRI"]
HVA_TO_MLU_STATIONS   = ["HVA", "PRI", "MLU"]

FREIGHT_OPS = {"vrc", "ferfi", "operail", "winco"}

# ---------------------------------------------------------------------------
# Part 3 — Constraint validators
# ---------------------------------------------------------------------------

def validate_block_signaling(df: pd.DataFrame):
    """
    WSP PDF p.22: block signaling is primitive; long intervals prevent
    better capacity utilisation. Uplift of 20-30% possible with ETCS/ERTMS.
    """
    print("\n" + "─" * 70)
    print("A. BLOCK SIGNALING INTERVALS (WSP p.22 — suojastusvälit)")
    print("─" * 70)
    print("Hypothesis: Minimum inter-train headways are unusually large,")
    print("confirming primitive block sections limit throughput by 20-30%.")

    segment_pairs = [
        ("TPE", "NOK", "TPE→NOK"),
        ("NOK", "KKI", "NOK→KKI (via Karkku/Siuro)"),
        ("KKI", "HVA", "KKI→HVA"),
        ("HVA", "PRI", "HVA→PRI"),
    ]

    all_headways = []
    for frm, to, label in segment_pairs:
        seg = compute_headways(df, frm, to, label)
        if seg.empty:
            print(f"  {label}: insufficient data")
            continue
        all_headways.append(seg)
        min_hw  = seg["headway_min"].min()
        mean_hw = seg["headway_min"].mean()
        p10_hw  = seg["headway_min"].quantile(0.10)
        count   = len(seg)
        print(f"\n  Segment: {label}  (n={count} consecutive pairs)")
        print(f"    Minimum headway      : {min_hw:.1f} min")
        print(f"    P10 headway          : {p10_hw:.1f} min  ← structural floor")
        print(f"    Mean headway         : {mean_hw:.1f} min")
        cap_now  = 60 / mean_hw if mean_hw > 0 else 0
        cap_etcs = cap_now * 1.25
        print(f"    Est. current capacity: {cap_now:.1f} trains/hr")
        print(f"    Est. ETCS capacity   : {cap_etcs:.1f} trains/hr (+25%)")

    if all_headways:
        combined    = pd.concat(all_headways)
        overall_min = combined["headway_min"].min()
        print(f"\n  → Corridor-wide structural minimum headway: {overall_min:.1f} min")
        if overall_min >= 10:
            verdict = "SUPPORTED — confirms large block sections restrict throughput"
        elif overall_min >= 6:
            verdict = "PARTIALLY SUPPORTED — some block constraint evident"
        else:
            verdict = "WEAK — headways tighter than expected for primitive signaling"
        print(f"  → WSP Correlation: {verdict}")


def validate_loop_length(df: pd.DataFrame):
    """
    WSP PDF p.22: Passing loops cannot handle 700m trains; freight standard
    is 750m. Trains longer than the loop bypass it, causing mainline conflicts.
    """
    print("\n" + "─" * 70)
    print("B. PASSING LOOP LENGTH LIMIT (WSP p.22 — 700m loop vs 750m freight)")
    print("─" * 70)

    loop_rows = df[
        (df["stationCode"].isin(PASSING_LOOP_STATIONS)) &
        (df["trainStopping"] == True) &
        (df["commercialStop"] == False)
    ].copy()

    if loop_rows.empty:
        print("  No technical stops recorded at loop stations in dataset.")
        return

    has_length = ("totalLength" in df.columns) and (df["totalLength"] > 0).any()

    if has_length:
        loop_rows["length_class"] = loop_rows["totalLength"].apply(
            lambda x: f">{LOOP_DESIGN_LIMIT_M}m (EXCEEDS LOOP)"
                      if x > LOOP_DESIGN_LIMIT_M
                      else (f"<={LOOP_DESIGN_LIMIT_M}m (fits)" if x > 0 else "unknown")
        )
        pivot = (
            loop_rows.groupby(["stationCode", "length_class"])
            .size()
            .unstack(fill_value=0)
        )
        print("  Technical stop counts by train length vs 700m design limit:")
        print(pivot.to_string())
        print()
        print("  Interpretation: rows showing '>700m EXCEEDS LOOP' with zero stops")
        print("  confirm those trains bypass the loop → mainline conflict forcing.")
    else:
        print("  (compositions not loaded — using traffic-profile proxy)")

        # Build trafficProfile column if absent
        if "trafficProfile" not in loop_rows.columns:
            loop_rows["trafficProfile"] = loop_rows["operatorCode"].apply(
                lambda x: "Freight/Cargo" if str(x).lower() in FREIGHT_OPS else "Passenger"
            )

        proxy = (
            loop_rows.groupby(["stationCode", "trafficProfile"])
            .agg(
                tech_stops=("trainStopping", "count"),
                avg_latency=("introduced_latency", "mean"),
                total_latency=("introduced_latency", "sum"),
            )
            .reset_index()
        )
        print(proxy.to_string(index=False))
        print()
        print("  Interpretation: if Freight/Cargo shows FEWER tech stops than Passenger")
        print("  at these loop stations, heavy trains are bypassing the short loops.")

        for stn in PASSING_LOOP_STATIONS:
            stn_data = proxy[proxy["stationCode"] == stn]
            if stn_data.empty:
                continue
            freq_pass  = stn_data[stn_data["trafficProfile"] == "Passenger"]["tech_stops"].sum()
            freq_cargo = stn_data[stn_data["trafficProfile"] == "Freight/Cargo"]["tech_stops"].sum()
            if freq_pass > 0:
                ratio = freq_cargo / freq_pass
                note  = "← freight bypassing loop (WSP p.22 confirmed)" if ratio < 0.5 else ""
                print(f"    {stn}: freight/passenger stop ratio = {ratio:.2f}  {note}")


def validate_axle_load_corridor(df: pd.DataFrame):
    """
    WSP PDF p.22: Axle weight limit is 22.5t on Kokemäki–Tahkoluoto.
    Forces operators to run shorter trains or use multiple locomotives.
    """
    print("\n" + "─" * 70)
    print("C. AXLE LOAD LIMIT (WSP p.22 — 22.5t on KKI–TAH vs 25t main line)")
    print("─" * 70)

    has_wagons = ("wagon_count" in df.columns) and (df["wagon_count"] > 0).any()

    freight_df = df[df["is_freight"] == True].copy() if "is_freight" in df.columns \
        else df[df["operatorCode"].str.lower().isin(FREIGHT_OPS)].copy()

    restricted_trains = set(
        freight_df[freight_df["stationCode"].isin(KKI_TO_POV_STATIONS)]["trainNumber"]
    )
    tpe_kki_only = set(
        freight_df[freight_df["stationCode"] == "TPE"]["trainNumber"]
    ) - restricted_trains

    if has_wagons:
        def profile(train_set, label):
            sub = (
                freight_df[freight_df["trainNumber"].isin(train_set)]
                [["trainNumber", "departureDate", "wagon_count",
                  "locomotive_count", "totalLength"]]
                .drop_duplicates()
            )
            if sub.empty:
                print(f"  {label}: no data")
                return
            print(f"\n  {label} (n={sub['trainNumber'].nunique()} trains):")
            print(f"    Avg wagon count     : {sub['wagon_count'].mean():.1f}")
            print(f"    Avg locomotive count: {sub['locomotive_count'].mean():.2f}")
            print(f"    Avg total length    : {sub['totalLength'].mean():.0f} m")
            multi_loco_pct = (sub["locomotive_count"] > 1).mean() * 100
            print(f"    Multi-loco ratio    : {multi_loco_pct:.1f}%")

        profile(restricted_trains, "Restricted corridor (KKI→TAH, 22.5t limit)")
        profile(tpe_kki_only,      "Reference segment   (TPE→KKI, 25t main line)")
        print()
        print("  Interpretation: fewer wagons and/or higher multi-loco ratio on")
        print("  restricted corridor confirms the axle limit is operationally active.")
    else:
        print("  (compositions not loaded — using delay-density proxy)")
        for seg_stations, label in [
            (KKI_TO_POV_STATIONS,   "Restricted  KKI→POV (22.5t)"),
            (["TPE", "LLH", "NOK"], "Reference   TPE→NOK (25t)"),
        ]:
            seg = freight_df[freight_df["stationCode"].isin(seg_stations)]
            if seg.empty:
                print(f"  {label}: no data")
                continue
            avg_lat   = seg["introduced_latency"].mean()
            tech_rate = (
                (seg["trainStopping"] == True) & (seg["commercialStop"] == False)
            ).mean() * 100
            print(f"  {label}: avg_latency={avg_lat:.2f}m, tech_stop_rate={tech_rate:.1f}%")
        print()
        print("  Interpretation: higher delay and tech-stop rate on the restricted")
        print("  segment supports the 22.5t operational friction claim.")


def validate_tahkoluoto_single_slot(df: pd.DataFrame):
    """
    WSP PDF p.7 & p.16: Tahkoluoto yard can unload only one train at a time.
    Simultaneous arrivals within a 60-minute window create measurable queuing.
    """
    print("\n" + "─" * 70)
    print("D. TAHKOLUOTO SINGLE-SLOT CONSTRAINT (WSP p.7 & p.16)")
    print("─" * 70)
    print("  Hypothesis: when ≥2 freight trains arrive within a 60-min window,")
    print("  one must queue, generating delay at TAH and upstream at HVA/KKI.")

    tah_arr = df[
        df["stationCode"].isin(["TAH", "POV", "TLU"]) &
        (df["rowType"] == "ARRIVAL") &
        (df["is_freight"] == True)
    ].copy()

    if tah_arr.empty:
        print("  No TAH/POV/TLU freight arrivals found.")
        print("  → Confirms POV NOT OBSERVABLE result (trains outside TPE query scope).")
        print("  → Recommendation: re-query Digitraffic with TAH as origin station.")
        _suggest_tah_query()
        return

    tah_arr["actual_dt"] = pd.to_datetime(tah_arr["actual"], errors="coerce", utc=True)
    tah_arr = tah_arr.dropna(subset=["actual_dt"]).sort_values("actual_dt").reset_index(drop=True)

    conflict_events = []
    for i, row in tah_arr.iterrows():
        window_start = row["actual_dt"] - pd.Timedelta(minutes=60)
        in_window = tah_arr[
            (tah_arr["actual_dt"] >= window_start) &
            (tah_arr["actual_dt"] < row["actual_dt"])
        ]
        if not in_window.empty:
            conflict_events.append({
                "date":               row["departureDate"],
                "arrival":            row["actual_dt"],
                "trains_in_window":   len(in_window),
                "introduced_latency": row["introduced_latency"],
            })

    if conflict_events:
        ce_df          = pd.DataFrame(conflict_events)
        conflict_rate  = len(ce_df) / len(tah_arr) * 100
        conflict_idx   = ce_df.index
        solo_mask      = ~tah_arr.index.isin(conflict_idx)

        avg_latency_conflict = ce_df["introduced_latency"].mean()
        avg_latency_solo     = tah_arr[solo_mask]["introduced_latency"].mean()

        print(f"\n  Total TAH freight arrivals    : {len(tah_arr)}")
        print(f"  Arrivals with conflict window : {len(ce_df)} ({conflict_rate:.1f}%)")
        print(f"  Avg latency — conflict trains : {avg_latency_conflict:.2f} min")
        print(f"  Avg latency — solo trains     : {avg_latency_solo:.2f} min")
        uplift = avg_latency_conflict - avg_latency_solo
        print(f"  Conflict latency premium      : +{uplift:.2f} min per arrival")
        if conflict_rate > 30:
            print("  → [SUPPORTED] Single-slot congestion is frequent and measurable.")
        elif conflict_rate > 10:
            print("  → [PARTIALLY SUPPORTED] Conflict events present but not dominant.")
        else:
            print("  → [WEAK] Conflict windows rare in available data.")
    else:
        print("  No conflict windows detected in available data.")


def _suggest_tah_query():
    print("""
  ── Corrected query fragment for Tahkoluoto ──────────────────────────────
  Add TAH as a direct station-origin query alongside the corridor OR-filter:

  {
    trainsByStationAndQuantity(
      station: "TAH",
      arrived_trains: 200,
      departed_trains: 200,
      include_nonstopping: false,
      train_categories: ["Cargo"]
    ) {
      trainNumber
      departureDate
      timeTableRows { ... }
    }
  }
  ─────────────────────────────────────────────────────────────────────────
""")


def validate_riihimaki_cascade(df: pd.DataFrame):
    """
    WSP PDF p.7 & p.16: Riihimäki–Tampere congestion cascades downstream.
    A late TPE arrival generates disproportionate delay at HVA/KKI/PRI.
    """
    print("\n" + "─" * 70)
    print("E. RIIHIMÄKI–TAMPERE CASCADE EFFECT (WSP p.7 & p.16)")
    print("─" * 70)
    print("  Hypothesis: freight trains arriving late at TPE generate")
    print("  disproportionately more delay downstream at HVA/KKI/PRI.")

    tpe_arr = df[
        (df["stationCode"] == "TPE") &
        (df["rowType"] == "ARRIVAL") &
        (df["is_freight"] == True)
    ][["trainNumber", "departureDate", "delayMinutes"]].rename(
        columns={"delayMinutes": "tpe_delay"}
    )

    downstream = (
        df[
            df["stationCode"].isin(["HVA", "KKI", "PRI"]) &
            (df["is_freight"] == True)
        ]
        .groupby(["trainNumber", "departureDate"])
        .agg(downstream_latency=("introduced_latency", "sum"))
        .reset_index()
    )

    merged = pd.merge(tpe_arr, downstream, on=["trainNumber", "departureDate"])

    if merged.empty or len(merged) < 10:
        print("  Insufficient data for cascade correlation analysis.")
        return

    late_threshold = 5
    on_time = merged[merged["tpe_delay"] <= late_threshold]
    late    = merged[merged["tpe_delay"] >  late_threshold]

    print(f"\n  On-time at TPE (≤{late_threshold}m late): n={len(on_time)}, "
          f"avg downstream latency = {on_time['downstream_latency'].mean():.2f} min")
    print(f"  Late at TPE   (>{late_threshold}m late): n={len(late)}, "
          f"avg downstream latency = {late['downstream_latency'].mean():.2f} min")

    if len(on_time) > 0 and len(late) > 0:
        baseline   = max(on_time["downstream_latency"].mean(), 0.01)
        multiplier = late["downstream_latency"].mean() / baseline
        print(f"\n  Cascade multiplier: {multiplier:.1f}x more downstream delay when TPE is late")
        if multiplier >= 2.0:
            print("  → [SUPPORTED] Strong cascade confirms WSP p.16 claim.")
        elif multiplier >= 1.3:
            print("  → [PARTIALLY SUPPORTED] Cascade present but moderate.")
        else:
            print("  → [WEAK] Little downstream amplification from TPE late arrivals.")

    corr = merged[["tpe_delay", "downstream_latency"]].corr().iloc[0, 1]
    print(f"\n  Pearson correlation (TPE delay vs downstream latency): r={corr:.3f}")
    if abs(corr) >= 0.5:
        print("  → Strong linear relationship — cascade is real and measurable.")
    elif abs(corr) >= 0.25:
        print("  → Moderate relationship — cascade exists but has other contributors.")
    else:
        print("  → Weak linear correlation — may be non-linear or time-shifted.")


def validate_harjavalta_industrial_spillover(df: pd.DataFrame):
    """
    WSP PDF p.7 & p.22: Harjavalta yard congested due to industrial shunting
    volume. Day-shift operations spill onto the main line.
    """
    print("\n" + "─" * 70)
    print("F. HARJAVALTA INDUSTRIAL SHUNTING SPILLOVER (WSP p.7 & p.22)")
    print("─" * 70)

    hva = df[
        (df["stationCode"] == "HVA") &
        (df["is_freight"] == True)
    ].copy()

    if hva.empty:
        print("  No HVA freight data available.")
        return

    hva["actual_dt"] = pd.to_datetime(hva["actual"], errors="coerce", utc=True)
    hva = hva.dropna(subset=["actual_dt"])
    hva["hour_local"] = (hva["actual_dt"] + pd.Timedelta(hours=2)).dt.hour
    hva["shift"] = hva["hour_local"].apply(
        lambda h: "day_shift (06-18)" if 6 <= h < 18 else "night (18-06)"
    )

    shift_stats = hva.groupby("shift").agg(
        events        =("introduced_latency", "count"),
        avg_latency   =("introduced_latency", "mean"),
        pct_delayed   =("introduced_latency", lambda x: (x > 0).mean() * 100),
        tech_stops    =("trainStopping", lambda x:
                        ((x == True) & (hva.loc[x.index, "commercialStop"] == False)).sum()),
    ).reset_index()

    print(shift_stats.to_string(index=False))

    day_row   = shift_stats[shift_stats["shift"].str.startswith("day")]
    night_row = shift_stats[shift_stats["shift"].str.startswith("night")]
    if not day_row.empty and not night_row.empty:
        ratio = day_row["avg_latency"].values[0] / max(night_row["avg_latency"].values[0], 0.001)
        print(f"\n  Day/night latency ratio at HVA: {ratio:.2f}x")
        if ratio >= 1.5:
            print("  → [SUPPORTED] Day-shift industrial ops cause measurable mainline spillover.")
        elif ratio >= 1.1:
            print("  → [PARTIALLY SUPPORTED] Elevated day delay but not strongly dominant.")
        else:
            print("  → [WEAK] No clear day/night pattern.")

    # Electrification dividend (requires compositions data)
    if "wagon_count" in df.columns and (df["wagon_count"] > 0).any():
        print("\n  ELECTRIFICATION DIVIDEND (WSP p.22: 40→48 wagons HVA–MLU)")
        hva_mlu = df[
            df["stationCode"].isin(HVA_TO_MLU_STATIONS) &
            (df["is_freight"] == True)
        ][["trainNumber", "departureDate", "wagon_count"]].drop_duplicates()

        if not hva_mlu.empty:
            over40 = (hva_mlu["wagon_count"] >= 40).mean() * 100
            over48 = (hva_mlu["wagon_count"] >= 48).mean() * 100
            print(f"    Trains with ≥40 wagons: {over40:.1f}%")
            print(f"    Trains with ≥48 wagons: {over48:.1f}%")
            print("    Rising ≥48 share confirms electrification benefit is being used.")