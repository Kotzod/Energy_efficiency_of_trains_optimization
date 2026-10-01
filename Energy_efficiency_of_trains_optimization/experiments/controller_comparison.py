"""Reproducible Rule-Based versus MPC experiment runner."""

import argparse
import csv
import json
from pathlib import Path

from infrastructure.railway_graph import RailwayModel


def run(controller: str, seed: int, max_ticks: int) -> dict:
    model = RailwayModel(seed=seed)
    model.set_controller_mode(controller)
    for _ in range(max_ticks):
        model.step()
    metrics = model.get_energy_metrics()
    return {"controller": controller, "seed": seed, "ticks": model.simulation_time, **metrics}


def compare(controllers=("rule_based", "mpc"), seeds=(67,), max_ticks=240):
    return [run(controller, seed, max_ticks) for seed in seeds for controller in controllers]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", nargs="+", type=int, default=[67])
    parser.add_argument("--ticks", type=int, default=240)
    parser.add_argument("--json", type=Path, default=Path("experiment_results.json"))
    parser.add_argument("--csv", type=Path, default=Path("experiment_results.csv"))
    args = parser.parse_args()
    rows = compare(seeds=args.seeds, max_ticks=args.ticks)
    args.json.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    with args.csv.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
