"""CLI-Schnittstelle.

Jeder Aufruf laedt den persistierten Zustand (.sgsim_state.json), fuehrt eine
Operation aus und schreibt ihn zurueck. Damit ist der Simulator zustandsbehaftet
zwischen einzelnen CLI-Aufrufen — Voraussetzung dafuer, dass Claude (oder ein
anderer externer Controller) das Grid Tick fuer Tick steuern kann.
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import click
import yaml

from .components import COMPONENT_REGISTRY, from_dict
from .engine import Grid
from .weather import SyntheticWeather


STATE_FILE = Path(".sgsim_state.json")


# ---------------------------------------------------------------------------
# Helfer
# ---------------------------------------------------------------------------

def _emit(payload: Any) -> None:
    """Strukturierte Ausgabe als JSON (ein Dokument pro Aufruf)."""
    click.echo(json.dumps(payload, indent=2, default=str))


def _require_state() -> Grid:
    if not STATE_FILE.exists():
        click.echo(
            json.dumps({"error": "no_state",
                        "hint": "zuerst 'sgsim init' aufrufen"}),
            err=True,
        )
        sys.exit(2)
    return Grid.load(STATE_FILE)


def _save(grid: Grid) -> None:
    grid.save(STATE_FILE)


# ---------------------------------------------------------------------------
# CLI-Gruppe
# ---------------------------------------------------------------------------

@click.group()
@click.version_option()
def cli() -> None:
    """sgsim — CLI-Smart-Grid-Simulator."""


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--scenario", type=click.Path(exists=True, dir_okay=False),
              default=None,
              help="Pfad zu einer Szenario-YAML (Default: eingebautes Beispiel).")
@click.option("--seed", type=int, default=None,
              help="Ueberschreibt den Seed aus dem Szenario.")
def init(scenario: str | None, seed: int | None) -> None:
    """Neuen Grid-Zustand anlegen (ueberschreibt bestehenden)."""
    if scenario is None:
        scenario = str(Path(__file__).parent / "scenarios" / "example.yaml")

    raw = yaml.safe_load(Path(scenario).read_text(encoding="utf-8"))

    weather = SyntheticWeather(
        seed=raw.get("seed", 42),
        **{k: v for k, v in raw.get("weather", {}).items()},
    )
    components = [from_dict(d) for d in raw.get("components", [])]

    grid = Grid(
        name=raw.get("name", "default"),
        seed=seed if seed is not None else raw.get("seed", 42),
        dt_min=raw.get("dt_min", 15),
        components=components,
        weather=weather,
    )
    _save(grid)
    _emit({
        "ok": True,
        "scenario": raw.get("name"),
        "seed": grid.seed,
        "dt_min": grid.dt_min,
        "components": [c.name for c in grid.components],
        "state_file": str(STATE_FILE.resolve()),
    })


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--full/--summary", default=False,
              help="Volle Historie ausgeben oder nur Zusammenfassung.")
def state(full: bool) -> None:
    """Aktuellen Grid-Zustand ausgeben."""
    grid = _require_state()
    if full:
        _emit(grid.to_dict())
        return
    _emit({
        "name": grid.name,
        "seed": grid.seed,
        "dt_min": grid.dt_min,
        "sim_time_h": grid.sim_time_h,
        "step_count": grid.step_count,
        "components": [c.to_dict() for c in grid.components],
        "last_tick": asdict(grid.history[-1]) if grid.history else None,
    })


# ---------------------------------------------------------------------------
# tick / run
# ---------------------------------------------------------------------------

@cli.command()
def tick() -> None:
    """Einen Zeitschritt ausfuehren und das Tick-Protokoll ausgeben."""
    grid = _require_state()
    rec = grid.tick()
    _save(grid)
    _emit(asdict(rec))


@cli.command()
@click.option("--steps", type=int, required=True, help="Anzahl Zeitschritte.")
def run(steps: int) -> None:
    """Mehrere Ticks am Stueck (ohne Eingriff)."""
    grid = _require_state()
    grid.run(steps)
    _save(grid)
    _emit({
        "ok": True,
        "executed_steps": steps,
        "step_count": grid.step_count,
        "sim_time_h": grid.sim_time_h,
        "metrics": grid.metrics(),
    })


# ---------------------------------------------------------------------------
# Eingriffe (Controller-Interface)
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("name")
@click.argument("value", type=float)
def set_curtailment(name: str, value: float) -> None:
    """PV-Abregelung 0..1 setzen (Controller-Aktion)."""
    if not 0.0 <= value <= 1.0:
        click.echo(json.dumps({"error": "value_out_of_range",
                               "hint": "0..1 erwartet"}), err=True)
        sys.exit(2)
    grid = _require_state()
    for c in grid.components:
        if c.name == name and hasattr(c, "curtailment"):
            c.curtailment = value
            _save(grid)
            _emit({"ok": True, "component": name, "curtailment": value})
            return
    click.echo(json.dumps({"error": "no_such_curtailable_component",
                           "name": name}), err=True)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Auswertung
# ---------------------------------------------------------------------------

@cli.command()
def metrics() -> None:
    """Aggregierte Messgroessen seit init ausgeben."""
    grid = _require_state()
    _emit(grid.metrics())


@cli.command()
@click.option("--out", type=click.Path(dir_okay=False), required=True)
def export(out: str) -> None:
    """Vollstaendiges Tick-Protokoll als CSV exportieren."""
    grid = _require_state()
    if not grid.history:
        click.echo(json.dumps({"error": "no_history"}), err=True)
        sys.exit(2)

    out_path = Path(out)
    comp_names = list(grid.history[0].components.keys())
    fieldnames = [
        "step", "sim_time_h", "hour_of_day",
        "irradiance", "wind", "temperature",
        "p_total_mw", "energy_in_mwh", "energy_out_mwh", "imbalance_mwh",
        *[f"P_{n}_mw" for n in comp_names],
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
            }
            for n in comp_names:
                row[f"P_{n}_mw"] = r.components.get(n, 0.0)
            w.writerow(row)
    _emit({"ok": True, "rows": len(grid.history), "out": str(out_path.resolve())})


if __name__ == "__main__":
    cli()
