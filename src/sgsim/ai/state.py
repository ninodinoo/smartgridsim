"""Grid-Zustand kompakt als JSON fuer einen externen KI-Decider serialisieren.

Die Snapshot-Funktion ist die Eingabe, die ein LLM-basierter Controller
(z. B. Claude ueber die Anthropic-API) pro Tick erhaelt. Sie ist bewusst
kompakt gehalten — nur was die KI fuer eine Entscheidung braucht. Die
volle Tick-Historie steckt im Engine-State und wird hier nicht ueber-
tragen, um Token-Kosten und Verarbeitung zu minimieren.

Schema:
    {
      "step": int,
      "sim_time_h": float,
      "dt_min": float,
      "weather_now":  {irradiance_w_m2, wind_m_s, temp_c},
      "weather_next": {irradiance_w_m2, wind_m_s, temp_c},
      "forecast_next_tick": {load_mw, renewable_mw},
      "components": {
         <name>: {type, p_now_mw, ...}    # Felder typabhaengig
      },
      "last_step":   {p_total_mw, imbalance_mwh, co2_kg, ...} | None
    }
"""

from __future__ import annotations

from typing import Any

from ..components import (
    BiomassPlant,
    CoalPlant,
    CommercialLoad,
    DispatchableGenerator,
    GasGuDPlant,
    IndustrialLoad,
    PVPlant,
    PumpedHydroStorage,
    ResidentialLoad,
    RunOfRiverHydro,
    Storage,
    TickContext,
    WindTurbine,
)
from ..engine import Grid


_NONDISPATCH_RENEWABLE_TYPES = (PVPlant, WindTurbine, RunOfRiverHydro)
_LOAD_TYPES = (ResidentialLoad, CommercialLoad, IndustrialLoad)


def _component_view(c: object) -> dict[str, Any]:
    """Pro Komponente die Felder, die die KI fuer eine Entscheidung braucht."""
    if isinstance(c, DispatchableGenerator):
        return {
            "type": "dispatchable_generator",
            "fuel": c.fuel,
            "p_now_mw": c.current_p_mw,
            "setpoint_mw": c.setpoint_mw,
            "p_min_mw": c.p_min_mw,
            "p_max_mw": c.p_max_mw,
            "ramp_mw_per_min": c.ramp_mw_per_min,
            "co2_kg_per_mwh": c.co2_kg_per_mwh,
        }
    if isinstance(c, Storage):
        return {
            "type": "pumped_hydro" if isinstance(c, PumpedHydroStorage) else "battery",
            "p_now_mw": 0.0,                      # echte Leistung kommt aus last_step
            "setpoint_mw": c.setpoint_mw,
            "soc_mwh": c.soc_mwh,
            "capacity_mwh": c.capacity_mwh,
            "min_soc_mwh": c.min_soc_mwh,
            "p_max_charge_mw": c.p_max_charge_mw,
            "p_max_discharge_mw": c.p_max_discharge_mw,
            "eta_charge": c.eta_charge,
            "eta_discharge": c.eta_discharge,
        }
    if isinstance(c, (PVPlant, WindTurbine)):
        return {
            "type": "pv" if isinstance(c, PVPlant) else "wind",
            "curtailment": c.curtailment,
        }
    if isinstance(c, RunOfRiverHydro):
        return {"type": "run_of_river"}
    if isinstance(c, _LOAD_TYPES):
        return {"type": "load"}
    return {"type": type(c).__name__}


def _forecast(grid: Grid, ctx: TickContext) -> dict[str, float]:
    """Erwartete Netto-Last und erneuerbare Erzeugung im naechsten Tick."""
    load_mw = 0.0
    renewable_mw = 0.0
    for c in grid.components:
        if isinstance(c, _LOAD_TYPES):
            load_mw += -c.step(grid.dt_h, ctx)         # Vorzeichenwechsel
        elif isinstance(c, _NONDISPATCH_RENEWABLE_TYPES):
            old = getattr(c, "curtailment", 0.0)
            if hasattr(c, "curtailment"):
                c.curtailment = 0.0
            renewable_mw += c.step(grid.dt_h, ctx)
            if hasattr(c, "curtailment"):
                c.curtailment = old
    return {"load_mw": load_mw, "renewable_mw": renewable_mw}


def grid_snapshot(grid: Grid, next_ctx: TickContext) -> dict[str, Any]:
    """Vollstaendiger Snapshot fuer den externen Decider."""
    weather_now = {
        "irradiance_w_m2": grid.weather.irradiance(grid.sim_time_h),
        "wind_m_s": grid.weather.wind_speed(grid.sim_time_h),
        "temp_c": grid.weather.temperature(grid.sim_time_h),
    }
    weather_next = {
        "irradiance_w_m2": next_ctx.irradiance_w_m2,
        "wind_m_s": next_ctx.wind_speed_m_s,
        "temp_c": next_ctx.temperature_c,
    }
    components = {c.name: _component_view(c) for c in grid.components}
    last_step: dict[str, Any] | None = None
    if grid.history:
        r = grid.history[-1]
        last_step = {
            "p_total_mw": r.p_total_mw,
            "imbalance_mwh": r.imbalance_mwh,
            "co2_kg": r.co2_kg,
            "renewable_energy_mwh": r.renewable_energy_mwh,
            "components_p_mw": r.components,
        }
    return {
        "step": grid.step_count,
        "sim_time_h": grid.sim_time_h,
        "hour_of_day": grid.sim_time_h % 24.0,
        "dt_min": grid.dt_min,
        "weather_now": weather_now,
        "weather_next": weather_next,
        "forecast_next_tick": _forecast(grid, next_ctx),
        "components": components,
        "last_step": last_step,
    }
