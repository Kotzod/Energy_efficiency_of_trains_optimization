"""Physically motivated train traction and energy calculations.

The model intentionally keeps infrastructure inputs optional for now. A future
track profile can provide ``gradient`` per edge without changing the public
calculation API.
"""

from dataclasses import dataclass

GRAVITY_MS2 = 9.81
AIR_DENSITY_KG_M3 = 1.225


@dataclass(frozen=True)
class TrainEnergyProfile:
    """Physical parameters used by the traction model."""

    mass_kg: float
    length_m: float
    maximum_speed_kmh: float
    maximum_acceleration_ms2: float
    maximum_braking_ms2: float
    traction_power_w: float
    rolling_resistance: float
    aerodynamic_coefficient: float
    frontal_area_m2: float
    traction_efficiency: float
    braking_efficiency: float
    auxiliary_power_w: float


@dataclass(frozen=True)
class EnergyStep:
    """Instantaneous power and energy changes for one simulation tick."""

    traction_force_n: float
    resistance_force_n: float
    braking_force_n: float
    power_w: float
    regenerated_power_w: float


def calculate_energy_step(
    profile: TrainEnergyProfile,
    speed_ms: float,
    acceleration_ms2: float,
    duration_s: float,
    *,
    gradient: float = 0.0,
    active: bool = True,
) -> EnergyStep:
    """Calculate traction draw and regenerative recovery for one time step.

    ``gradient`` is expressed as a ratio, e.g. ``0.008`` for an 0.8% climb.
    Positive acceleration requires traction force; braking produces recovery
    rather than positive traction draw. Auxiliary load is included while the
    train is active, including while stationary at a station.
    """
    del duration_s  # Reserved for future time-varying profiles.
    speed_ms = max(0.0, speed_ms)
    if not active:
        return EnergyStep(0.0, 0.0, 0.0, 0.0, 0.0)

    rolling_force = profile.mass_kg * GRAVITY_MS2 * profile.rolling_resistance
    aerodynamic_force = (
        0.5
        * AIR_DENSITY_KG_M3
        * profile.aerodynamic_coefficient
        * profile.frontal_area_m2
        * speed_ms**2
    )
    gradient_force = profile.mass_kg * GRAVITY_MS2 * gradient
    resistance_force = rolling_force + aerodynamic_force + gradient_force

    traction_force = 0.0
    braking_force = 0.0
    regenerated_power = 0.0

    if acceleration_ms2 > 0.0 and speed_ms > 0.0:
        traction_force = min(
            profile.mass_kg * acceleration_ms2 + max(0.0, resistance_force),
            profile.traction_power_w / speed_ms,
        )
    elif acceleration_ms2 < 0.0 and speed_ms > 0.0:
        braking_force = profile.mass_kg * abs(acceleration_ms2)
        regenerated_power = (
            braking_force * speed_ms * profile.braking_efficiency
        )

    traction_power = 0.0
    if traction_force > 0.0:
        traction_power = traction_force * speed_ms / max(profile.traction_efficiency, 1e-6)

    return EnergyStep(
        traction_force_n=traction_force,
        resistance_force_n=resistance_force,
        braking_force_n=braking_force,
        power_w=traction_power + profile.auxiliary_power_w,
        regenerated_power_w=regenerated_power,
    )
