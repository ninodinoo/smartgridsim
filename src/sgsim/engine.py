"""Simulations-Engine: haelt den Netzzustand, fuehrt Ticks aus, sammelt Metriken."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .components import (
    BiomassPlant,
    Component,
    DispatchableGenerator,
    GeothermalPlant,
    PVPlant,
    RunOfRiverHydro,
    Storage,
    TickContext,
    WindTurbine,
    from_dict,
)
from .frequency import F_NOMINAL_HZ, FrequencyState
from .weather import SyntheticWeather


DEFAULT_DT_MIN = 15.0  # Standard-Zeitschritt: 15 Minuten

# Komponententypen, deren Energie als "erneuerbar erzeugt" zaehlt.
# Hinweis: HydrogenGasTurbine zaehlt NICHT mit, da der H2-Brennstoff ueber
# einen Speicher rueckverstromt wird, dessen Renewable-Anteil bereits beim
# Laden gebucht wurde (sonst Doppelzaehlung).
RENEWABLE_TYPES: tuple[type[Component], ...] = (
    PVPlant, WindTurbine, RunOfRiverHydro, BiomassPlant, GeothermalPlant,
)


@dataclass
class TickRecord:
    """Eine Zeile des Mess-Logs (ein Tick)."""

    step: int
    sim_time_h: float
    hour_of_day: float
    irradiance: float
    wind: float
    temperature: float
    components: dict[str, float]                  # name -> P [MW]
    component_details: dict[str, dict[str, float]]  # name -> snapshot()
    p_total_mw: float
    energy_in_mwh: float                          # Σ(P>0) * dt
    energy_out_mwh: float                         # Σ(|P|<0) * dt
    imbalance_mwh: float                          # P_total * dt
    co2_kg: float                                 # CO2-Emissionen dieses Ticks
    renewable_energy_mwh: float                   # erneuerbar erzeugte Energie
    frequency_hz: float                           # Netzfrequenz nach diesem Tick
    frequency_deviation_hz: float                 # |f - 50 Hz|


@dataclass
class Grid:
    """Container fuer Komponenten + Simulationszustand."""

    name: str = "default"
    seed: int = 42
    dt_min: float = DEFAULT_DT_MIN
    sim_time_h: float = 0.0
    step_count: int = 0
    components: list[Component] = field(default_factory=list)
    weather: SyntheticWeather = field(default_factory=lambda: SyntheticWeather())
    frequency: FrequencyState = field(default_factory=FrequencyState)
    history: list[TickRecord] = field(default_factory=list)

    @property
    def dt_h(self) -> float:
        return self.dt_min / 60.0

    # -------------------------------------------------------------------
    # Lookups
    # -------------------------------------------------------------------

    def find(self, name: str) -> Component:
        for c in self.components:
            if c.name == name:
                return c
        raise KeyError(name)

    # -------------------------------------------------------------------
    # Tick
    # -------------------------------------------------------------------

    def tick(self) -> TickRecord:
        """Einen Zeitschritt ausfuehren."""
        h_of_day = self.sim_time_h % 24.0
        ctx = TickContext(
            sim_time_h=self.sim_time_h,
            hour_of_day=h_of_day,
            irradiance_w_m2=self.weather.irradiance(self.sim_time_h),
            wind_speed_m_s=self.weather.wind_speed(self.sim_time_h),
            temperature_c=self.weather.temperature(self.sim_time_h),
        )

        per_comp: dict[str, float] = {}
        per_comp_details: dict[str, dict[str, float]] = {}
        e_in = 0.0
        e_out = 0.0
        p_total = 0.0
        co2_kg = 0.0
        e_renewable = 0.0
        for c in self.components:
            p = c.step(self.dt_h, ctx)
            per_comp[c.name] = p
            details = c.snapshot()
            if details:
                per_comp_details[c.name] = details
            p_total += p
            if p >= 0.0:
                e_in += p * self.dt_h
            else:
                e_out += -p * self.dt_h

            # CO2 nur fuer dispatchierbare Generatoren mit Faktor
            if isinstance(c, DispatchableGenerator) and p > 0.0:
                co2_kg += p * self.dt_h * c.co2_kg_per_mwh

            # Renewable-Buchhaltung: erneuerbare Komponenten + Speicher beim Entladen
            # zaehlen wir konservativ NICHT zu erneuerbar (Speicher kann fossil
            # geladen worden sein). Reine Erneuerbare zaehlen nur wenn P > 0.
            if isinstance(c, RENEWABLE_TYPES) and p > 0.0:
                e_renewable += p * self.dt_h

        # Frequenz nachfuehren (vereinfachte Swing-Equation).
        # dt in Sekunden fuer das Frequenzmodell.
        f_hz = self.frequency.step(p_total, self.dt_h * 3600.0)

        rec = TickRecord(
            step=self.step_count,
            sim_time_h=self.sim_time_h,
            hour_of_day=h_of_day,
            irradiance=ctx.irradiance_w_m2,
            wind=ctx.wind_speed_m_s,
            temperature=ctx.temperature_c,
            components=per_comp,
            component_details=per_comp_details,
            p_total_mw=p_total,
            energy_in_mwh=e_in,
            energy_out_mwh=e_out,
            imbalance_mwh=p_total * self.dt_h,
            co2_kg=co2_kg,
            renewable_energy_mwh=e_renewable,
            frequency_hz=f_hz,
            frequency_deviation_hz=abs(f_hz - F_NOMINAL_HZ),
        )
        self.history.append(rec)
        self.sim_time_h += self.dt_h
        self.step_count += 1
        return rec

    def run(self, n_steps: int) -> list[TickRecord]:
        return [self.tick() for _ in range(n_steps)]

    # -------------------------------------------------------------------
    # Aggregierte Metriken
    # -------------------------------------------------------------------

    def metrics(self) -> dict[str, Any]:
        if not self.history:
            return {"steps": 0}
        e_in = sum(r.energy_in_mwh for r in self.history)
        e_out = sum(r.energy_out_mwh for r in self.history)
        e_ren = sum(r.renewable_energy_mwh for r in self.history)
        co2 = sum(r.co2_kg for r in self.history)

        # Brownouts: Zeitschritte mit unterdecktem Bedarf (P_total < 0).
        # Aequivalent zu nicht gedeckter Last in MWh.
        deficit_mwh = sum(
            -r.imbalance_mwh for r in self.history if r.imbalance_mwh < 0
        )
        surplus_mwh = sum(
            r.imbalance_mwh for r in self.history if r.imbalance_mwh > 0
        )
        brownout_steps = sum(1 for r in self.history if r.imbalance_mwh < 0)

        peak_load = max(
            (-r.p_total_mw for r in self.history if r.p_total_mw < 0),
            default=0.0,
        )
        max_surplus = max(
            (r.p_total_mw for r in self.history if r.p_total_mw > 0),
            default=0.0,
        )

        # Frequenz-Statistik
        max_freq_dev = max((r.frequency_deviation_hz for r in self.history),
                           default=0.0)
        ticks_outside_dead_band = sum(
            1 for r in self.history if r.frequency_deviation_hz > 0.2
        )

        return {
            "steps": len(self.history),
            "sim_hours": self.sim_time_h,
            "energy_generated_mwh": e_in,
            "energy_consumed_mwh": e_out,
            "renewable_energy_mwh": e_ren,
            "renewable_share_of_demand": (e_ren / e_out) if e_out > 0 else 0.0,
            "co2_kg": co2,
            "co2_kg_per_mwh_demand": (co2 / e_out) if e_out > 0 else 0.0,
            "unserved_energy_mwh": deficit_mwh,
            "surplus_energy_mwh": surplus_mwh,
            "brownout_steps": brownout_steps,
            "peak_deficit_mw": peak_load,
            "peak_surplus_mw": max_surplus,
            "max_frequency_deviation_hz": max_freq_dev,
            "ticks_outside_freq_dead_band": ticks_outside_dead_band,
        }

    # -------------------------------------------------------------------
    # Persistenz
    # -------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "seed": self.seed,
            "dt_min": self.dt_min,
            "sim_time_h": self.sim_time_h,
            "step_count": self.step_count,
            "components": [c.to_dict() for c in self.components],
            "weather": asdict(self.weather) | {"_class": "SyntheticWeather"},
            "frequency": asdict(self.frequency),
            "history": [asdict(r) for r in self.history],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Grid":
        weather_data = dict(data["weather"])
        weather_data.pop("_class", None)
        weather_data.pop("_rng", None)
        weather = SyntheticWeather(**weather_data)

        components = [from_dict(d) for d in data["components"]]
        history = [TickRecord(**r) for r in data.get("history", [])]

        freq_data = data.get("frequency", {})
        frequency = FrequencyState(**freq_data) if freq_data else FrequencyState()

        return cls(
            name=data["name"],
            seed=data["seed"],
            dt_min=data["dt_min"],
            sim_time_h=data["sim_time_h"],
            step_count=data["step_count"],
            components=components,
            weather=weather,
            frequency=frequency,
            history=history,
        )

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Grid":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
