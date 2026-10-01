from typing import List, Literal
from pydantic import BaseModel, Field


class ParameterItem(BaseModel):
    key: str = Field(description="Machine-readable mutation parameter name.")
    value: str = Field(description="Mutation parameter represented as a string.")


class EnvironmentalLayer(BaseModel):
    weather: Literal[
        "Clear", "Light rain", "Heavy rain", "Light snow", "Heavy snow",
        "Freezing rain / ice", "Strong wind", "Extreme heat (>35 °C rail temp)",
    ] = "Clear"
    temperature_celsius: float = 20.0
    visibility_meters: float = 10000.0
    precipitation_mm_per_hour: float = 0.0
    wind_speed_kmh: float = 0.0
    notes: str = ""


class FleetMatchingCriteria(BaseModel):
    train_id: str = ""
    train_type: str = ""
    operator: str = ""
    route_id: str = ""
    origin_station: str = ""
    destination_station: str = ""
    priority_class: str = ""
    notes: str = ""


class InfrastructureMutation(BaseModel):
    target_id: str
    anomaly_type: Literal[
        "switch_failure", "station_failure", "switch_clamp",
        "tower_failure", "speed_restriction", "track_blockage",
    ]
    severity: float = 1.0
    trigger_tick: int = 0
    parameters: List[ParameterItem] = Field(default_factory=list)


class TelecomMutation(BaseModel):
    target_id: str
    anomaly_type: Literal["tower_failure"]
    severity: float = 1.0
    trigger_tick: int = 0
    parameters: List[ParameterItem] = Field(default_factory=list)


class DispatchMutation(BaseModel):
    target_id: str
    anomaly_type: Literal[
        "track_blockage", "speed_restriction", "dispatch_hold", "route_hold",
        "priority_override", "passing_loop_hold",
    ]
    severity: float = 1.0
    trigger_tick: int = 0
    parameters: List[ParameterItem] = Field(default_factory=list)


class FleetMutationItem(BaseModel):
    matching_criteria: FleetMatchingCriteria = Field(default_factory=FleetMatchingCriteria)
    anomaly_type: Literal[
        "train_delay", "speed_reduction", "emergency_stop", "engine_breakdown",
    ]
    severity: float = 1.0
    trigger_tick: int = 0
    parameters: List[ParameterItem] = Field(default_factory=list)


class RailwayScenarioSchema(BaseModel):
    reasoning: str
    environmental_layer: EnvironmentalLayer = Field(default_factory=EnvironmentalLayer)
    infrastructure_mutations: List[InfrastructureMutation] = Field(default_factory=list)
    telecom_signaling_mutations: List[TelecomMutation] = Field(default_factory=list)
    dispatch_mutations: List[DispatchMutation] = Field(default_factory=list)
    fleet_mutations: List[FleetMutationItem] = Field(default_factory=list)
