"""Compile natural-language scenarios into validated model mutations."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from pydantic import ValidationError

from infrastructure.railway_graph import RailwayModel
from .schema_mapper import RailwayScenarioSchema


SYSTEM_PROMPT = """
Convert the railway incident into RailwayScenarioSchema JSON. Extract every
explicit disruption. Put weather in environmental_layer, physical failures
in infrastructure_mutations, radio failures in telecom_signaling_mutations,
dispatch instructions in dispatch_mutations, and train-specific changes in
fleet_mutations. Preserve identifiers. Use trigger_tick 0 for immediate
changes. Use speed_factor for speed changes and blocked_edge only when known.
Return short mapping rationale in reasoning; do not provide hidden reasoning.
"""


def _load_environment() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        return
    except ModuleNotFoundError:
        pass
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.lstrip().startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))


def convert_prompt_to_config(user_prompt: str) -> RailwayScenarioSchema:
    """Ask Gemini for structured output and validate it with schema_mapper."""
    _load_environment()
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("google-genai is required for scenario prompts") from exc

    client = genai.Client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=RailwayScenarioSchema,
            temperature=0.0,
        ),
    )
    if not response.text:
        raise RuntimeError("Gemini returned an empty scenario response")
    try:
        return RailwayScenarioSchema.model_validate_json(response.text)
    except ValidationError as exc:
        raise ValueError(f"Scenario did not match RailwayScenarioSchema: {exc}") from exc


def _parameter_dict(mutation: Dict[str, Any]) -> Dict[str, str]:
    parameters = {}
    for item in mutation.get("parameters", []):
        key = item.get("key") if isinstance(item, dict) else item.key
        value = item.get("value") if isinstance(item, dict) else item.value
        if key:
            parameters[key] = value
    return parameters


def _station_id(model: RailwayModel, target: str) -> str:
    aliases = {
        "tampere": "TPE", "lielahti": "LLH", "nokia": "NOA", "siuro": "SIU",
        "sammalisto": "SNM", "karkku": "KRU", "hameenkyro": "HNO",
        "hämeenkyrö": "HNO", "viljakkala": "VMA", "kokemaki": "KKI",
        "kokemäki": "KKI", "harjavalta": "HVA", "nakkila": "NAL",
        "ulvila": "ULV", "pori": "PRI",
    }
    normalized = str(target).strip().lower().replace("-", " ").replace("_", " ")
    for suffix in (" station", " asema", " railway station"):
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]
            break
    return aliases.get(normalized, str(target).strip().upper())


def _tower_id(model: RailwayModel, target: str) -> str | None:
    towers = getattr(model, "radio_towers", {})
    normalized = str(target).strip().lower().replace("-", "_").replace(" ", "_")
    for tower_id in towers:
        if normalized == str(tower_id).lower().replace("-", "_").replace(" ", "_"):
            return tower_id
    if normalized.startswith("tower_") and normalized[6:].isdigit():
        index = int(normalized[6:]) - 1
        keys = list(towers)
        return keys[index] if 0 <= index < len(keys) else None
    return None


def _apply_mutation(model: RailwayModel, category: str, mutation: Dict[str, Any]) -> None:
    params = _parameter_dict(mutation)
    target = str(mutation.get("target_id", ""))
    anomaly = mutation.get("anomaly_type", "")

    if category == "infrastructure":
        station = _station_id(model, target)
        if anomaly == "switch_failure":
            switches = model.get_switches(station)
            index = params.get("switch_index")
            indices = [int(index)] if index is not None else range(max(1, round(len(switches) * float(mutation.get("severity", 1.0)))))
            for switch_index in indices:
                model.fail_switch(station, switch_index)
        elif anomaly == "station_failure":
            model.fail_station_switches(station)
        elif anomaly == "switch_clamp":
            for index in range(len(model.get_switches(station))):
                model.clamp_switch(station, index, params.get("clamp_position", "normal"))
        elif anomaly == "track_blockage":
            model.blocked_edges = getattr(model, "blocked_edges", set())
            model.blocked_edges.add(params.get("blocked_edge", target))
        elif anomaly == "speed_restriction":
            model.speed_restrictions = getattr(model, "speed_restrictions", {})
            model.speed_restrictions[station] = {"factor": float(params.get("speed_factor", "0.5"))}
    elif category == "telecom" and anomaly == "tower_failure":
        resolved = _tower_id(model, target)
        if resolved is None:
            raise ValueError(f"Unknown radio tower: {target}")
        model.fail_radio_tower(resolved)
    elif category == "dispatch":
        if anomaly == "track_blockage":
            model.blocked_edges = getattr(model, "blocked_edges", set())
            model.blocked_edges.add(params.get("blocked_edge", target))
        elif anomaly in {"dispatch_hold", "route_hold", "passing_loop_hold"}:
            model.dispatch_holds = getattr(model, "dispatch_holds", set())
            model.dispatch_holds.add(target)
        elif anomaly == "priority_override":
            model.dispatch_priority_overrides = getattr(model, "dispatch_priority_overrides", {})
            model.dispatch_priority_overrides[target] = int(params.get("priority", "1"))
        elif anomaly == "speed_restriction":
            model.dispatch_speed_restrictions = getattr(model, "dispatch_speed_restrictions", {})
            model.dispatch_speed_restrictions[target] = float(params.get("speed_factor", "0.5"))
    elif category == "fleet":
        criteria = mutation.get("matching_criteria", {})
        for agent in getattr(model, "agents", []):
            if criteria.get("train_id") and str(agent.unique_id) != criteria["train_id"]:
                continue
            if criteria.get("train_type") and agent.train_type != criteria["train_type"]:
                continue
            if anomaly == "train_delay":
                agent.wait_time += int(params.get("delay_ticks", "10"))
            elif anomaly == "speed_reduction":
                agent.scenario_speed_factor = float(params.get("speed_factor", "0.5"))
            elif anomaly == "emergency_stop":
                agent.scenario_emergency_stop = True
                agent.current_speed_ms = 0.0
            elif anomaly == "engine_breakdown":
                agent.engine_broken = True
                agent.current_speed_ms = 0.0


def apply_single_mutation(model: RailwayModel, category: str, mutation: Dict[str, Any]) -> None:
    """Apply one schema mutation when RailwayModel reaches its trigger tick."""
    _apply_mutation(model, category, mutation)


def apply_mutations_to_model(model: RailwayModel, config: Dict[str, Any]) -> RailwayModel:
    env = config.get("environmental_layer", {})
    model.current_weather = env.get("weather", "Clear")
    model.current_temperature_celsius = env.get("temperature_celsius", 20.0)
    model.current_visibility_meters = env.get("visibility_meters", 10000.0)
    model.current_precipitation_mm_per_hour = env.get("precipitation_mm_per_hour", 0.0)
    model.current_wind_speed_kmh = env.get("wind_speed_kmh", 0.0)
    model.current_weather_notes = env.get("notes", "")
    model.pending_mutations = []
    groups = (("infrastructure_mutations", "infrastructure"), ("telecom_signaling_mutations", "telecom"), ("dispatch_mutations", "dispatch"), ("fleet_mutations", "fleet"))
    for key, category in groups:
        for mutation in config.get(key, []):
            item = {"trigger_tick": int(mutation.get("trigger_tick", 0)), "category": category, "mutation": mutation}
            if item["trigger_tick"] <= model.simulation_time:
                _apply_mutation(model, category, mutation)
            else:
                model.pending_mutations.append(item)
    model.pending_mutations.sort(key=lambda item: item["trigger_tick"])
    return model


def run_railway_simulation(scenario_text: str) -> Dict[str, Any]:
    """Parse a prompt, validate it with the schema, and transfer it to a model."""
    try:
        parsed = convert_prompt_to_config(scenario_text)
        config = parsed.model_dump()
        model = apply_mutations_to_model(RailwayModel(seed=67), config)
        return {"model": model, "config": config, "error": None}
    except Exception as exc:
        return {"model": None, "config": None, "error": f"Failed to translate scenario: {exc}"}
