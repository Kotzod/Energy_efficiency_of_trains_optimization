from infrastructure.railway_graph import RailwayModel


def test_model_exposes_energy_metrics_after_a_tick():
    model = RailwayModel(seed=67)
    model.step()

    metrics = model.get_energy_metrics()

    assert metrics["activeTrains"] == 2
    assert metrics["totalPowerW"] > 0.0
    assert metrics["totalEnergyConsumedKwh"] > 0.0
    assert metrics["totalEnergyRegeneratedKwh"] >= 0.0
    assert metrics["totalNetEnergyKwh"] >= 0.0
    assert metrics["energyPerKm"] > 0.0

    train = next(iter(model.agents))
    assert train.get_status()["power_w"] >= 0.0
    assert train.get_status()["energy_consumed_kwh"] >= 0.0
