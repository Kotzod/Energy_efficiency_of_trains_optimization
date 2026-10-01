"""
scenario_experiments.py

Single-file experiment harness for the Tampere-Pori RailwayModel: runs a
baseline plus a set of scripted disruption scenarios (switch failure,
snowstorm, radio tower outage, and a combination), collects per-tick and
per-train data, measures each disruption point's criticality via paired
baseline/scenario replications, prints comparison tables, and saves CSVs
(+ charts, if matplotlib is available).

Drop this file at your project root, next to model.py, so the `agents`
and `infrastructure` packages it imports resolve the same way they do
for the rest of your code.

BEFORE RUNNING, edit the CONFIG section below if you want to investigate
different infrastructure points. The defaults refer to configured HNO and
BS_009 assets in this repository.
    - SNOWSTORM_WEATHER_NAME: must match a key under "weather" in
        infrastructure/weather_config.json.
  - DEFAULT_REPAIR_TICKS: this is a MODELLING PARAMETER, not verified
    real-world data -- I couldn't find a citable, switch-specific
    mean-time-to-repair figure. Treat it as something to source from
    real data if you have access to any, or sweep it (see
    REPAIR_TICKS_SWEEP below) and report how recovery scales with it.

KNOWN LIMITATION: the snowstorm scenario sets model.current_weather,
which TrainAgent._get_weather_factors() reads live -- so it correctly
affects train speed/accel/braking. It does NOT affect switch failure
probability: Switch.update_operational_time() reads its own
module-level WEATHER_CONFIG in infrastructure/switch.py, loaded once
at import time, independent of the model instance -- and as far as I
can see from your model.py, update_operational_time() isn't even being
called from RailwayModel.step() yet, so stochastic weather-driven
switch failure isn't wired in at all currently. If you want a storm to
also raise switch failure odds, either call update_operational_time()
on your switches somewhere in step(), or mutate
infrastructure.switch.WEATHER_CONFIG["current_weather"] directly in
the scenario functions below (fragile, since it's shared module
state -- fine for a single-process experiment run, not for anything
concurrent).
"""

import os
import statistics
from dataclasses import dataclass, field

import pandas as pd

# --- adjust this import to match your project's actual module path ---
from infrastructure.railway_graph import RailwayModel


# ============================================================
# CONFIG -- edit these to match your project
# ============================================================

N_TICKS = 180                  # simulation length per run, in ticks (minutes, since time_step=1)
TIME_STEP_MINUTES = 1
N_REPLICATIONS = 5             # independent seeded runs per scenario/point
BASE_SEED = 1000

DISRUPTION_START_TICK = 50
DEFAULT_REPAIR_TICKS = 60      # one hour at the default one-minute time step
REPAIR_TICKS_SWEEP = [15, 60, 240]   # 15 minutes, 1 hour, and 4 hours

# Must match a key under "weather" in infrastructure/weather_config.json.
SNOWSTORM_WEATHER_NAME = "Heavy snow"

# Fill these in with real (station_id, switch_index) pairs and real
# radio tower IDs from your own config files -- these are placeholders.
CANDIDATE_RADIO_TOWERS = ["BS_009"]

OUTPUT_DIR = "scenario_results"


# ============================================================
# CORE RUNNER
# ============================================================

def run_scenario(scenario_events, seed, n_ticks=N_TICKS, time_step_minutes=TIME_STEP_MINUTES):
    """
    Run one simulation with a scripted list of interventions.

    scenario_events: list of (trigger_tick, callable) pairs, e.g.
        [(50, lambda m: m.fail_switch("KAU", 0)),
         (110, lambda m: m.repair_switch("KAU", 0))]
    Events fire at the START of their tick, before that tick's agents act.
    """
    model = RailwayModel(time_step_minutes=time_step_minutes, seed=seed)
    model.datacollector.collect(model)
    events = sorted(scenario_events, key=lambda e: e[0])
    idx = 0

    for tick in range(n_ticks):
        while idx < len(events) and events[idx][0] <= tick:
            events[idx][1](model)
            idx += 1
        model.step()

    model_df = model.datacollector.get_model_vars_dataframe()
    agent_df = model.datacollector.get_agent_vars_dataframe()
    return model_df, agent_df


# ============================================================
# SCENARIO DEFINITIONS
# ============================================================
# Each builder takes repair_ticks so every switch can be tested at each
# configured repair duration.

def scenario_baseline(repair_ticks=None):
    return []


def scenario_switch_failure(station_id, switch_index, repair_ticks=DEFAULT_REPAIR_TICKS):
    return [
        (DISRUPTION_START_TICK, lambda m: m.fail_switch(station_id, switch_index)),
        (DISRUPTION_START_TICK + repair_ticks, lambda m: m.repair_switch(station_id, switch_index)),
    ]


def scenario_snowstorm(repair_ticks=DEFAULT_REPAIR_TICKS):
    def _start(m):
        m._scenario_previous_weather = m.current_weather
        m.current_weather = SNOWSTORM_WEATHER_NAME

    def _end(m):
        m.current_weather = getattr(m, "_scenario_previous_weather", "Clear")

    return [
        (DISRUPTION_START_TICK, _start),
        (DISRUPTION_START_TICK + repair_ticks, _end),
    ]


def scenario_radio_tower_outage(tower_id, repair_ticks=DEFAULT_REPAIR_TICKS):
    return [
        (DISRUPTION_START_TICK, lambda m: m.fail_radio_tower(tower_id)),
        (DISRUPTION_START_TICK + repair_ticks, lambda m: m.repair_radio_tower(tower_id)),
    ]


def scenario_combo_snowstorm_and_switch(station_id, switch_index, repair_ticks=DEFAULT_REPAIR_TICKS):
    return scenario_snowstorm(repair_ticks) + scenario_switch_failure(station_id, switch_index, repair_ticks)


def discover_switch_points():
    """Return every configured switch as a (station_id, switch_index) pair."""
    model = RailwayModel(seed=BASE_SEED)
    return [
        (station_id, switch_index)
        for station_id, switches in model.switches.items()
        for switch_index in range(len(switches))
    ]


# ============================================================
# METRICS
# ============================================================

def excess_delay(baseline_df, scenario_df):
    """Per-step scenario-minus-baseline, aligned by collected model step."""
    merged = baseline_df[["trains_waiting", "total_delay_ticks"]].join(
        scenario_df[["trains_waiting", "total_delay_ticks"]],
        lsuffix="_base", rsuffix="_scenario",
    )
    merged["excess_waiting"] = merged["trains_waiting_scenario"] - merged["trains_waiting_base"]
    merged["excess_delay_ticks"] = merged["total_delay_ticks_scenario"] - merged["total_delay_ticks_base"]
    return merged


def recovery_tick(excess_df, disruption_start_tick=DISRUPTION_START_TICK + 1, stable_ticks=5):
    """
    First tick after disruption start where excess_waiting has returned to
    <= 0 and held for `stable_ticks` in a row. None if it never does within
    the run.
    """
    after = excess_df.loc[disruption_start_tick:]
    stable = (after["excess_waiting"] <= 0).rolling(stable_ticks).sum() == stable_ticks
    hits = stable[stable]
    return hits.index.min() if not hits.empty else None


@dataclass
class ScenarioResult:
    name: str
    excess_delay_ticks: list = field(default_factory=list)
    recovery_minutes: list = field(default_factory=list)   # None entries = never recovered within run

    def summary(self):
        recovered = [r for r in self.recovery_minutes if r is not None]
        return {
            "scenario": self.name,
            "mean_excess_delay_ticks": round(statistics.mean(self.excess_delay_ticks), 1) if self.excess_delay_ticks else 0,
            "stdev_excess_delay_ticks": round(statistics.pstdev(self.excess_delay_ticks), 1) if len(self.excess_delay_ticks) > 1 else 0,
            "mean_recovery_minutes": round(statistics.mean(recovered), 1) if recovered else None,
            "runs_never_recovered": len(self.recovery_minutes) - len(recovered),
            "n_replications": len(self.excess_delay_ticks),
        }


def run_named_scenario(name, event_builder, n_replications=N_REPLICATIONS, base_seed=BASE_SEED):
    """
    event_builder: zero-arg callable returning a scenario_events list
    (use a lambda/closure to bind station/tower args before passing it in).
    """
    result = ScenarioResult(name=name)
    for rep in range(n_replications):
        seed = base_seed + rep
        baseline_df, _ = run_scenario([], seed=seed)
        scenario_df, _ = run_scenario(event_builder(), seed=seed)

        excess = excess_delay(baseline_df, scenario_df)
        result.excess_delay_ticks.append(
            float(excess["excess_delay_ticks"].clip(lower=0).sum())
        )

        rec_tick = recovery_tick(excess)
        rec_minutes = (
            float(rec_tick - (DISRUPTION_START_TICK + 1)) * TIME_STEP_MINUTES
            if rec_tick is not None else None
        )
        result.recovery_minutes.append(rec_minutes)

    return result


# ============================================================
# CRITICALITY
# ============================================================

def measure_switch_criticality(points=None, repair_ticks_list=REPAIR_TICKS_SWEEP,
                               n_replications=N_REPLICATIONS, base_seed=BASE_SEED):
    """Test every switch at every configured repair duration and rank results."""
    points = discover_switch_points() if points is None else list(points)
    rankings = []
    for station_id, switch_index in points:
        for repair_ticks in repair_ticks_list:
            result = run_named_scenario(
                f"switch:{station_id}#{switch_index}@{repair_ticks}min",
                lambda station_id=station_id, switch_index=switch_index, repair_ticks=repair_ticks: scenario_switch_failure(
                    station_id, switch_index, repair_ticks
                ),
                n_replications=n_replications, base_seed=base_seed,
            )
            row = result.summary()
            row["point"] = f"{station_id} (switch {switch_index})"
            row["repair_minutes"] = repair_ticks * TIME_STEP_MINUTES
            rankings.append(row)
    rankings.sort(key=lambda r: r["mean_excess_delay_ticks"], reverse=True)
    return rankings


def measure_radio_tower_criticality(towers=CANDIDATE_RADIO_TOWERS, n_replications=N_REPLICATIONS, base_seed=BASE_SEED):
    rankings = []
    for tower_id in towers:
        result = run_named_scenario(
            f"tower:{tower_id}",
            lambda tower_id=tower_id: scenario_radio_tower_outage(tower_id),
            n_replications=n_replications, base_seed=base_seed,
        )
        row = result.summary()
        row["point"] = f"radio tower {tower_id}"
        rankings.append(row)
    rankings.sort(key=lambda r: r["mean_excess_delay_ticks"], reverse=True)
    return rankings


# ============================================================
# OPTIONAL: repair-time sensitivity sweep
# ============================================================

def sweep_repair_time(station_id, switch_index, repair_ticks_list=REPAIR_TICKS_SWEEP,
                       n_replications=N_REPLICATIONS, base_seed=BASE_SEED):
    """
    Run the repair-duration comparison for one selected switch.
    The main criticality analysis uses the same logic for every switch.
    """
    rows = []
    for repair_ticks in repair_ticks_list:
        result = run_named_scenario(
            f"switch:{station_id}#{switch_index}@{repair_ticks}ticks",
            lambda repair_ticks=repair_ticks: scenario_switch_failure(station_id, switch_index, repair_ticks),
            n_replications=n_replications, base_seed=base_seed,
        )
        row = result.summary()
        row["repair_ticks"] = repair_ticks
        rows.append(row)
    return rows


# ============================================================
# DISPLAY
# ============================================================

def print_table(rows, columns, title):
    print(f"\n{title}")
    print("-" * len(title))
    if not rows:
        print("(no data)")
        return
    widths = {c: max(len(c), *(len(f"{r.get(c, '')}") for r in rows)) for c in columns}
    header = " | ".join(c.ljust(widths[c]) for c in columns)
    print(header)
    print("-" * len(header))
    for r in rows:
        print(" | ".join(f"{r.get(c, '')}".ljust(widths[c]) for c in columns))


def save_and_plot(scenario_rows, criticality_rows, sweep_rows=None, output_dir=OUTPUT_DIR):
    os.makedirs(output_dir, exist_ok=True)
    sweep_rows = sweep_rows or []

    scenario_df = pd.DataFrame(scenario_rows)
    scenario_df.to_csv(os.path.join(output_dir, "scenario_comparison.csv"), index=False)

    criticality_df = pd.DataFrame(criticality_rows)
    criticality_df.to_csv(os.path.join(output_dir, "point_criticality.csv"), index=False)

    sweep_df = pd.DataFrame(sweep_rows)
    if not sweep_df.empty:
        sweep_df.to_csv(os.path.join(output_dir, "repair_time_sweep.csv"), index=False)

    try:
        import matplotlib.pyplot as plt

        if not scenario_df.empty:
            fig, ax = plt.subplots(figsize=(8, 4.5))
            ax.bar(scenario_df["scenario"], scenario_df["mean_excess_delay_ticks"],
                   yerr=scenario_df["stdev_excess_delay_ticks"])
            ax.set_ylabel("Mean excess delay (train-ticks vs baseline)")
            ax.set_title("Scenario comparison")
            plt.xticks(rotation=30, ha="right")
            fig.tight_layout()
            fig.savefig(os.path.join(output_dir, "scenario_comparison.png"))
            plt.close(fig)

        if not criticality_df.empty:
            fig, ax = plt.subplots(figsize=(8, 4.5))
            ax.barh(criticality_df["point"], criticality_df["mean_excess_delay_ticks"])
            ax.set_xlabel("Mean excess delay caused (train-ticks vs baseline)")
            ax.set_title("Point criticality ranking")
            fig.tight_layout()
            fig.savefig(os.path.join(output_dir, "point_criticality.png"))
            plt.close(fig)

        if not sweep_df.empty:
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))
            ax1.plot(sweep_df["repair_ticks"], sweep_df["mean_excess_delay_ticks"], marker="o")
            ax1.set_xlabel("Repair duration (ticks)")
            ax1.set_ylabel("Mean excess delay (train-ticks vs baseline)")
            ax1.set_title("Delay vs repair duration")

            ax2.plot(sweep_df["repair_ticks"], sweep_df["mean_recovery_minutes"], marker="o", color="tab:orange")
            ax2.set_xlabel("Repair duration (ticks)")
            ax2.set_ylabel("Mean recovery time (minutes)")
            ax2.set_title("Recovery time vs repair duration")

            fig.tight_layout()
            fig.savefig(os.path.join(output_dir, "repair_time_sweep.png"))
            plt.close(fig)

        print(f"\nCharts saved to {output_dir}/")
    except ImportError:
        print("\n(matplotlib not installed -- skipping charts, CSVs were still saved)")


# ============================================================
# MAIN
# ============================================================

def main():
    scenario_rows = []
    switch_points = discover_switch_points()
    first_switch = switch_points[0] if switch_points else None

    # Sanity check: a scenario with no events, compared to a real baseline,
    # should show ~0 excess delay everywhere. If it doesn't, something
    # about the model isn't fully seed-deterministic and the rest of these
    # comparisons won't be trustworthy.
    scenario_rows.append(run_named_scenario("sanity_check_baseline_vs_itself", scenario_baseline).summary())

    if first_switch:
        scenario_rows.append(run_named_scenario(
            "switch_failure",
            lambda: scenario_switch_failure(*first_switch),
        ).summary())
        scenario_rows.append(run_named_scenario(
            "combo_snowstorm+switch_failure",
            lambda: scenario_combo_snowstorm_and_switch(*first_switch),
        ).summary())

    scenario_rows.append(run_named_scenario("snowstorm", scenario_snowstorm).summary())

    if CANDIDATE_RADIO_TOWERS:
        scenario_rows.append(run_named_scenario(
            "radio_tower_outage",
            lambda: scenario_radio_tower_outage(CANDIDATE_RADIO_TOWERS[0]),
        ).summary())

    print_table(
        scenario_rows,
        ["scenario", "mean_excess_delay_ticks", "stdev_excess_delay_ticks",
         "mean_recovery_minutes", "runs_never_recovered", "n_replications"],
        "Scenario comparison",
    )

    criticality_rows = measure_switch_criticality(switch_points) + measure_radio_tower_criticality()
    criticality_rows.sort(key=lambda r: r["mean_excess_delay_ticks"], reverse=True)

    print_table(
        criticality_rows,
        ["point", "repair_minutes", "mean_excess_delay_ticks", "mean_recovery_minutes", "runs_never_recovered"],
        "Point criticality ranking (highest impact first)",
    )

    sweep_rows = []

    save_and_plot(scenario_rows, criticality_rows, sweep_rows)


if __name__ == "__main__":
    main()