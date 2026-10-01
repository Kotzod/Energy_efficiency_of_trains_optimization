from physics.train_energy import TrainEnergyProfile, calculate_energy_step


PROFILE = TrainEnergyProfile(
    mass_kg=420_000,
    length_m=160,
    maximum_speed_kmh=140,
    maximum_acceleration_ms2=0.8,
    maximum_braking_ms2=1.2,
    traction_power_w=4_000_000,
    rolling_resistance=0.0015,
    aerodynamic_coefficient=0.8,
    frontal_area_m2=10.0,
    traction_efficiency=0.90,
    braking_efficiency=0.80,
    auxiliary_power_w=120_000,
)


def test_stationary_train_has_auxiliary_load_but_no_traction_force():
    result = calculate_energy_step(PROFILE, 0.0, 0.0, 60.0)

    assert result.traction_force_n == 0.0
    assert result.power_w == PROFILE.auxiliary_power_w


def test_acceleration_consumes_positive_power():
    result = calculate_energy_step(PROFILE, 20.0, 0.8, 60.0)

    assert result.traction_force_n > 0.0
    assert result.power_w > PROFILE.auxiliary_power_w
    assert result.regenerated_power_w == 0.0


def test_regenerative_braking_reports_recovered_power():
    result = calculate_energy_step(PROFILE, 20.0, -0.8, 60.0)

    assert result.traction_force_n == 0.0
    assert result.regenerated_power_w > 0.0
    assert result.power_w == PROFILE.auxiliary_power_w


def test_gradient_increases_resistance():
    level = calculate_energy_step(PROFILE, 20.0, 0.0, 60.0, gradient=0.0)
    climb = calculate_energy_step(PROFILE, 20.0, 0.0, 60.0, gradient=0.008)

    assert climb.resistance_force_n > level.resistance_force_n
