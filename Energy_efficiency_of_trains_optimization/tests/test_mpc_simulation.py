import logging

from infrastructure.railway_graph import RailwayModel


def _run(mode: str, seed: int = 67, ticks: int = 240):
    logging.disable(logging.CRITICAL)
    model = RailwayModel(seed=seed)
    model.set_controller_mode(mode)
    for _ in range(ticks):
        model.step()
    return model


def test_mpc_run_moves_trains_and_records_actual_distance():
    model = _run("mpc")
    metrics = model.get_energy_metrics()

    assert model.simulation_time == 240
    assert sum(train.distance_traveled_km for train in model.agents) > 0.0
    assert metrics["totalEnergyConsumedKwh"] > 0.0
    assert metrics["movingTrains"] + metrics["stoppedTrains"] == metrics["activeTrains"]
    assert metrics["averageSpeedKmh"] >= 0.0


def test_controller_runs_use_same_tick_and_initial_seed_contract():
    rule = _run("rule_based", seed=67)
    mpc = _run("mpc", seed=67)

    assert rule.simulation_time == mpc.simulation_time == 240
    assert len(rule.agents) == len(mpc.agents)
    assert rule.agents[0].route == mpc.agents[0].route
    assert rule.agents[0].energy_profile == mpc.agents[0].energy_profile


def test_mpc_does_not_report_planned_saving_as_measured_energy():
    model = _run("mpc", ticks=12)
    measured = sum(train.energy_consumed_kwh for train in model.agents)
    planned = sum(train.last_decision_saving_kwh for train in model.agents)

    assert model.get_energy_metrics()["totalEnergyConsumedKwh"] == measured
    assert measured >= 0.0
    assert planned >= 0.0
    assert model.get_energy_metrics()["totalEnergyConsumedKwh"] != planned
