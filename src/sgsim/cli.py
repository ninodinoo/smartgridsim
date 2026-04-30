"""CLI-Schnittstelle.

Jeder Aufruf laedt den persistierten Zustand (.sgsim_state.json), fuehrt eine
Operation aus und schreibt ihn zurueck. Damit ist der Simulator zustandsbehaftet
zwischen einzelnen CLI-Aufrufen — Voraussetzung dafuer, dass ein externer
Controller (z. B. Claude oder ein regelbasiertes Skript) das Grid Tick fuer
Tick steuern kann.
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

from .components import from_dict
from .controllers import CONTROLLER_REGISTRY
from .engine import Grid
from .experiment import (
    build_grid,
    compare_runs,
    export_csv,
    run_experiment,
    write_metrics_sidecar,
)
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


def _set_attr_if_present(obj: object, attr: str, value: float) -> bool:
    if hasattr(obj, attr):
        setattr(obj, attr, value)
        return True
    return False


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
        scenario = str(Path(__file__).parent / "scenarios" / "stadt_mittel.yaml")

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
        "components": [
            {"name": c.name, "type": type(c).__name__}
            for c in grid.components
        ],
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
    components_info = []
    for c in grid.components:
        info = {"name": c.name, "type": type(c).__name__}
        info.update(c.snapshot())
        components_info.append(info)
    _emit({
        "name": grid.name,
        "seed": grid.seed,
        "dt_min": grid.dt_min,
        "sim_time_h": grid.sim_time_h,
        "step_count": grid.step_count,
        "components": components_info,
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
    """PV-/Wind-Abregelung 0..1 setzen (Controller-Aktion)."""
    if not 0.0 <= value <= 1.0:
        click.echo(json.dumps({"error": "value_out_of_range",
                               "hint": "0..1 erwartet"}), err=True)
        sys.exit(2)
    grid = _require_state()
    try:
        c = grid.find(name)
    except KeyError:
        click.echo(json.dumps({"error": "no_such_component",
                               "name": name}), err=True)
        sys.exit(2)
    if not _set_attr_if_present(c, "curtailment", value):
        click.echo(json.dumps({"error": "not_curtailable",
                               "name": name, "type": type(c).__name__}), err=True)
        sys.exit(2)
    _save(grid)
    _emit({"ok": True, "component": name, "curtailment": value})


@cli.command()
@click.argument("name")
@click.argument("mw", type=float)
def dispatch(name: str, mw: float) -> None:
    """Sollwert eines dispatchierbaren Erzeugers oder Speichers setzen.

    Konventionen:
      - Erzeuger:  positiv = Einspeisung
      - Speicher:  positiv = Entladen, negativ = Laden
    """
    grid = _require_state()
    try:
        c = grid.find(name)
    except KeyError:
        click.echo(json.dumps({"error": "no_such_component",
                               "name": name}), err=True)
        sys.exit(2)
    if not _set_attr_if_present(c, "setpoint_mw", mw):
        click.echo(json.dumps({"error": "not_dispatchable",
                               "name": name, "type": type(c).__name__}),
                   err=True)
        sys.exit(2)
    _save(grid)
    _emit({"ok": True, "component": name, "setpoint_mw": mw,
           "type": type(c).__name__})


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
    """Vollstaendiges Tick-Protokoll als CSV exportieren.

    Pro Komponente werden zwei Sorten Spalten geschrieben:
      P_<name>_mw                  Wirkleistung im Tick
      D_<name>_<feld>              Detail-Felder aus snapshot() (z. B. SoC)
    """
    grid = _require_state()
    if not grid.history:
        click.echo(json.dumps({"error": "no_history"}), err=True)
        sys.exit(2)

    out_path = Path(out)
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
    _emit({"ok": True, "rows": len(grid.history), "out": str(out_path.resolve())})


# ---------------------------------------------------------------------------
# experiment-Subgruppe
# ---------------------------------------------------------------------------

@cli.group()
def experiment() -> None:
    """Self-contained Experimente fuer den Strategie-Vergleich."""


@experiment.command("run")
@click.option("--scenario", type=click.Path(exists=True, dir_okay=False),
              default=None,
              help="Pfad zur Szenario-YAML (Default: stadt_mittel).")
@click.option("--controller", "controller_name",
              type=click.Choice(["none", *CONTROLLER_REGISTRY.keys()]),
              default="rule_based",
              help="Welche Steuerungsstrategie soll gefahren werden?")
@click.option("--steps", type=int, default=96,
              help="Anzahl Zeitschritte (Default 96 = 24 h).")
@click.option("--seed", type=int, default=None,
              help="Wetter-Seed (ueberschreibt den im Szenario).")
@click.option("--out", type=click.Path(dir_okay=False), required=True,
              help="Pfad fuer CSV-Output (eine Zeile je Tick).")
def experiment_run(scenario: str | None, controller_name: str,
                   steps: int, seed: int | None, out: str) -> None:
    """Einen vollstaendigen Vergleichslauf ausfuehren."""
    if scenario is None:
        scenario = str(Path(__file__).parent / "scenarios" / "stadt_mittel.yaml")
    grid, _ctrl = run_experiment(Path(scenario), controller_name, steps, seed)
    out_path = Path(out)
    rows = export_csv(grid, out_path)
    sidecar = write_metrics_sidecar(grid, out_path, controller_name)
    _emit({
        "ok": True,
        "controller": controller_name,
        "scenario": grid.name,
        "seed": grid.seed,
        "steps": steps,
        "rows": rows,
        "out": str(out_path.resolve()),
        "metrics_sidecar": str(sidecar.resolve()),
        "metrics": grid.metrics(),
    })


@experiment.command("compare")
@click.argument("csv_paths", nargs=-1, type=click.Path(exists=True, dir_okay=False))
def experiment_compare(csv_paths: tuple[str, ...]) -> None:
    """Mehrere Runs gegenueberstellen.

    Der erste Pfad ist die Baseline; weitere Runs werden in Prozent-Differenz
    zur Baseline ausgegeben.
    """
    if len(csv_paths) < 2:
        click.echo(json.dumps({"error": "need_two_runs",
                               "hint": "mindestens zwei CSV-Pfade angeben"}),
                   err=True)
        sys.exit(2)
    result = compare_runs([Path(p) for p in csv_paths])
    _emit(result)


if __name__ == "__main__":
    cli()
