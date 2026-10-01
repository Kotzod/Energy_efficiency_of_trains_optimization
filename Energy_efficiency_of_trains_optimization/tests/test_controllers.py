from controllers.energy_controller import ACTIONS, MPCController, RuleBasedController
from infrastructure.railway_graph import RailwayModel


def test_rule_based_controller_returns_valid_action():
    model = RailwayModel(seed=67)
    train = next(iter(model.agents))
    decision = RuleBasedController().decide(train)
    assert decision.action in ACTIONS
    assert decision.reason


def test_mpc_controller_returns_valid_action_without_bypassing_model():
    model = RailwayModel(seed=67)
    model.set_controller_mode("mpc")
    model.step()
    assert model.controller_mode == "mpc"
    assert all(agent.last_decision in ACTIONS for agent in model.agents)


def test_experiment_modes_are_reproducible_for_same_seed():
    first = RailwayModel(seed=67)
    second = RailwayModel(seed=67)
    first.set_controller_mode("mpc")
    second.set_controller_mode("mpc")
    first.step()
    second.step()
    assert first.get_energy_metrics() == second.get_energy_metrics()
