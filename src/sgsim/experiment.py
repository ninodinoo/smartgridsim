"""Self-contained Experiment-Runner.

Im Gegensatz zum interaktiven CLI-Modus (state-Datei + ein Tick pro Aufruf)
laeuft hier der gesamte Vergleich in einem Prozess: Szenario laden, Controller
einsetzen, n Ticks rechnen, Metriken/CSV schreiben. Das ist die uebliche Form,
in der die Baseline-Strategien (naive, rule_based) gegen die KI gemessen werden.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from .components import TickContext, from_dict
from .controllers import CONTROLLER_REGISTRY, Controller
from .engine import Grid
from .weather import SyntheticWeather


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def build_grid(scenario_path: Path, seed: int | None = None) -> Grid:
    raw = yaml.safe_load(scenario_path.read_text(encoding="utf-8"))
    weather_seed = seed if seed is not None else raw.get("seed", 42)
    weather = SyntheticWeather(
        seed=weather_seed,
        **{k: v for k, v in raw.get("weather", {}).items()},
    )
    components = [from_dict(d) for d in raw.get("components", [])]
    return Grid(
        name=raw.get("name", "default"),
        seed=weather_seed,
        dt_min=raw.get("dt_min", 15),
        components=components,
        weather=weather,
    )


def _next_ctx(grid: Grid) -> TickContext:
    """Wetter-/Zeit-Kontext fuer den naechsten Tick (Forecast-Eingabe)."""
    t = grid.sim_time_h
    return TickContext(
        sim_time_h=t,
        hour_of_day=t % 24.0,
        irradiance_w_m2=grid.weather.irradiance(t),
        wind_speed_m_s=grid.weather.wind_speed(t),
        temperature_c=grid.weather.temperature(t),
    )


def run_experiment(
    scenario_path: Path,
    controller_name: str,
    steps: int,
    seed: int | None = None,
) -> tuple[Grid, Controller | None]:
    grid = build_grid(scenario_path, seed=seed)
    controller: Controller | None = None
    if controller_name != "none":
        cls = CONTROLLER_REGISTRY[controller_name]
        controller = cls()
        controller.initialize(grid)
    for _ in range(steps):
        if controller is not None:
            controller.step(grid, _next_ctx(grid))
        grid.tick()
    return grid, controller


# ---------------------------------------------------------------------------
# CSV-Export (frei, ohne State-File)
# ---------------------------------------------------------------------------

def export_csv(grid: Grid, out_path: Path) -> int:
    if not grid.history:
        out_path.write_text("", encoding="utf-8")
        return 0

    comp_names = list(grid.history[0].components.keys())
    detail_fields: list[tuple[str, str]] = []
    for r in grid.history:
        for cname, det in r.component_details.items():
            for k in det.keys():
                key = (cname, k)
                if key not in detail_fields:
                    detail_fields.append(key)

    fieldnames = [
        "step", "sim_time_h", "hour_of_day",
        "irradiance", "wind", "temperature",
        "p_total_mw", "energy_in_mwh", "energy_out_mwh", "imbalance_mwh",
        "co2_kg", "renewable_energy_mwh",
        *[f"P_{n}_mw" for n in comp_names],
        *[f"D_{c}_{k}" for c, k in detail_fields],
    ]
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in grid.history:
            row = {
                "step": r.step, "sim_time_h": r.sim_time_h,
                "hour_of_day": r.hour_of_day,
                "irradiance": r.irradiance, "wind": r.wind,
                "temperature": r.temperature,
                "p_total_mw": r.p_total_mw,
                "energy_in_mwh": r.energy_in_mwh,
                "energy_out_mwh": r.energy_out_mwh,
                "imbalance_mwh": r.imbalance_mwh,
                "co2_kg": r.co2_kg,
                "renewable_energy_mwh": r.renewable_energy_mwh,
            }
            for n in comp_names:
                row[f"P_{n}_mw"] = r.components.get(n, 0.0)
            for c, k in detail_fields:
                row[f"D_{c}_{k}"] = r.component_details.get(c, {}).get(k, "")
            w.writerow(row)
    return len(grid.history)


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------

# Metriken, die wir aus einem CSV rekonstruieren / aus JSON-Sidecar lesen
COMPARE_KEYS = (
    "energy_consumed_mwh",
    "energy_generated_mwh",
    "renewable_energy_mwh",
    "renewable_share_of_demand",
    "co2_kg",
    "co2_kg_per_mwh_demand",
    "unserved_energy_mwh",
    "surplus_energy_mwh",
    "brownout_steps",
    "peak_deficit_mw",
    "peak_surplus_mw",
)


def aggregate_metrics(grid: Grid) -> dict[str, Any]:
    return grid.metrics() | {"controller": None, "scenario": grid.name,
                             "seed": grid.seed}


def write_metrics_sidecar(grid: Grid, csv_path: Path,
                          controller_name: str) -> Path:
    sidecar = csv_path.with_suffix(".metrics.json")
    payload = aggregate_metrics(grid)
    payload["controller"] = controller_name
    sidecar.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return sidecar


def load_metrics_sidecar(csv_path: Path) -> dict[str, Any]:
    sidecar = csv_path.with_suffix(".metrics.json")
    if not sidecar.exists():
        raise FileNotFoundError(
            f"Erwartete Metriken-Datei {sidecar} nicht gefunden — "
            f"Run mit 'experiment run' erzeugen."
        )
    return json.loads(sidecar.read_text(encoding="utf-8"))


def compare_runs(csv_paths: list[Path]) -> dict[str, Any]:
    """Zwei oder mehr Runs gegenueberstellen.

    Rueckgabe: dict mit per-Run-Metriken und den prozentualen Aenderungen
    relativ zum ersten Run (Baseline).
    """
    runs = []
    for p in csv_paths:
        m = load_metrics_sidecar(p)
        runs.append({"path": str(p), **m})

    baseline = runs[0]
    deltas = []
    for r in runs[1:]:
        delta: dict[str, Any] = {"path": r["path"], "controller": r.get("controller")}
        for k in COMPARE_KEYS:
            b = baseline.get(k)
            v = r.get(k)
            if b in (None, 0) or v is None:
                delta[k + "_pct"] = None
            else:
                delta[k + "_pct"] = (v - b) / abs(b) * 100.0
        deltas.append(delta)

    return {
        "baseline": baseline,
        "runs": runs,
        "deltas_vs_baseline_pct": deltas,
    }
