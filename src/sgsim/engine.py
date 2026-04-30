"""Simulations-Engine: haelt den Netzzustand, fuehrt Ticks aus, sammelt Metriken."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .components import Component, TickContext, from_dict
from .weather import SyntheticWeather


DEFAULT_DT_MIN = 15.0  # Standard-Zeitschritt: 15 Minuten


@dataclass
class TickRecord:
    """Eine Zeile des Mess-Logs (ein Tick)."""

    step: int
    sim_time_h: float
    hour_of_day: float
    irradiance: float
    wind: float
    temperature: float
    components: dict[str, float]       # name -> P [MW]
    p_total_mw: float                  # algebraische Summe (Erzeugung - Last)
    energy_in_mwh: float               # Σ(P>0) * dt
    energy_out_mwh: float              # Σ(|P|<0) * dt
    imbalance_mwh: float               # P_total * dt (>0: Ueberschuss, <0: Defizit)


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
    history: list[TickRecord] = field(default_factory=list)

    @property
    def dt_h(self) -> float:
        return self.dt_min / 60.0

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
        e_in = 0.0
        e_out = 0.0
        p_total = 0.0
        for c in self.components:
            p = c.step(self.dt_h, ctx)
            per_comp[c.name] = p
            p_total += p
            if p >= 0.0:
                e_in += p * self.dt_h
            else:
                e_out += -p * self.dt_h

        rec = TickRecord(
            step=self.step_count,
            sim_time_h=self.sim_time_h,
            hour_of_day=h_of_day,
            irradiance=ctx.irradiance_w_m2,
            wind=ctx.wind_speed_m_s,
            temperature=ctx.temperature_c,
            components=per_comp,
            p_total_mw=p_total,
            energy_in_mwh=e_in,
            energy_out_mwh=e_out,
            imbalance_mwh=p_total * self.dt_h,
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
        peak_load = max((-r.p_total_mw for r in self.history if r.p_total_mw < 0),
                        default=0.0)
        max_surplus = max((r.p_total_mw for r in self.history if r.p_total_mw > 0),
                          default=0.0)
        return {
            "steps": len(self.history),
            "sim_hours": self.sim_time_h,
            "energy_generated_mwh": e_in,
            "energy_consumed_mwh": e_out,
            "net_imbalance_mwh": e_in - e_out,
            "peak_deficit_mw": peak_load,
            "peak_surplus_mw": max_surplus,
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
            "history": [asdict(r) for r in self.history],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Grid":
        weather_data = dict(data["weather"])
        weather_data.pop("_class", None)
        # private RNG-State wird aus seed neu aufgebaut (deterministisch)
        weather_data.pop("_rng", None)
        weather = SyntheticWeather(**weather_data)

        components = [from_dict(d) for d in data["components"]]
        history = [TickRecord(**r) for r in data.get("history", [])]

        return cls(
            name=data["name"],
            seed=data["seed"],
            dt_min=data["dt_min"],
            sim_time_h=data["sim_time_h"],
            step_count=data["step_count"],
            components=components,
            weather=weather,
            history=history,
        )

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "Grid":
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
