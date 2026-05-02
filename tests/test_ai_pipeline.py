"""Tests fuer die KI-Steuerungspipeline (Snapshot, Apply, RandomAIController)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sgsim.ai import apply_action, grid_snapshot
from sgsim.ai.controllers import (
    AnthropicAIController,
    RandomAIController,
    _parse_action_json,
)
from sgsim.experiment import _next_ctx, build_grid, run_experiment


SCENARIO = Path(__file__).parent.parent / "src" / "sgsim" / "scenarios" / "stadt_mittel.yaml"


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def test_snapshot_contains_required_fields() -> None:
    grid = build_grid(SCENARIO, seed=42)
    snap = grid_snapshot(grid, _next_ctx(grid))
    for key in ("step", "sim_time_h", "dt_min",
                "weather_now", "weather_next",
                "forecast_next_tick", "components"):
        assert key in snap, f"missing {key}"
    assert snap["forecast_next_tick"]["load_mw"] >= 0
    assert snap["forecast_next_tick"]["renewable_mw"] >= 0


def test_snapshot_components_typed() -> None:
    grid = build_grid(SCENARIO, seed=42)
    snap = grid_snapshot(grid, _next_ctx(grid))
    types = {info["type"] for info in snap["components"].values()}
    # mindestens diese Typen muessen im Standardszenario vorkommen
    for t in ("dispatchable_generator", "battery", "pumped_hydro",
              "hydrogen_storage", "pv", "wind", "load"):
        assert t in types, f"type {t!r} missing in snapshot"


def test_snapshot_serializable_to_json() -> None:
    grid = build_grid(SCENARIO, seed=42)
    grid.tick()
    snap = grid_snapshot(grid, _next_ctx(grid))
    # Muss verlustfrei JSON-serialisierbar sein
    s = json.dumps(snap)
    snap2 = json.loads(s)
    assert snap2["step"] == 1


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def test_apply_setpoint() -> None:
    grid = build_grid(SCENARIO, seed=42)
    warnings = apply_action(
        grid,
        {"actions": [{"component": "h2_gasturbine", "setpoint_mw": 100.0}]},
    )
    assert warnings == []
    h2 = next(c for c in grid.components if c.name == "h2_gasturbine")
    assert h2.setpoint_mw == 100.0


def test_apply_curtailment() -> None:
    grid = build_grid(SCENARIO, seed=42)
    warnings = apply_action(
        grid,
        {"actions": [{"component": "pv_aufdach", "curtailment": 0.5}]},
    )
    assert warnings == []
    pv = next(c for c in grid.components if c.name == "pv_aufdach")
    assert pv.curtailment == 0.5


def test_apply_invalid_component_warns() -> None:
    grid = build_grid(SCENARIO, seed=42)
    warnings = apply_action(
        grid,
        {"actions": [{"component": "kein_solches_kraftwerk", "setpoint_mw": 1.0}]},
    )
    assert len(warnings) == 1
    assert "unknown" in warnings[0]


def test_apply_invalid_curtailment_clamps_and_warns() -> None:
    grid = build_grid(SCENARIO, seed=42)
    warnings = apply_action(
        grid,
        {"actions": [{"component": "pv_aufdach", "curtailment": 2.0}]},
    )
    assert any("out of range" in w for w in warnings)
    pv = next(c for c in grid.components if c.name == "pv_aufdach")
    assert pv.curtailment == 1.0


def test_apply_setpoint_on_pv_warns() -> None:
    grid = build_grid(SCENARIO, seed=42)
    warnings = apply_action(
        grid,
        {"actions": [{"component": "pv_aufdach", "setpoint_mw": 50.0}]},
    )
    assert any("not dispatchable" in w for w in warnings)


# ---------------------------------------------------------------------------
# RandomAIController — End-to-End-Lauf
# ---------------------------------------------------------------------------

def test_random_ai_runs_without_crash() -> None:
    grid, _ = run_experiment(SCENARIO, "random_ai", steps=96, seed=42)
    assert grid.step_count == 96


def test_random_ai_is_worse_than_rule_based() -> None:
    """Wissenschaftliche Erwartung: zufaellige Steuerung versorgt schlechter
    als eine regelbasierte. Das ist ein dritter Vergleichspunkt fuer die Arbeit.
    """
    g_rb, _ = run_experiment(SCENARIO, "rule_based", steps=96, seed=42)
    g_rand, _ = run_experiment(SCENARIO, "random_ai", steps=96, seed=42)
    # Mindestens eines der beiden Mass-Kriterien muss klar zugunsten rule_based ausfallen
    assert (g_rand.metrics()["co2_kg"] > g_rb.metrics()["co2_kg"]
            or g_rand.metrics()["unserved_energy_mwh"]
               > g_rb.metrics()["unserved_energy_mwh"])


# ---------------------------------------------------------------------------
# JSON-Parser-Robustheit
# ---------------------------------------------------------------------------

def test_parse_action_plain_json() -> None:
    res = _parse_action_json('{"actions": [{"component": "x", "setpoint_mw": 1}]}')
    assert res == {"actions": [{"component": "x", "setpoint_mw": 1}]}


def test_parse_action_with_markdown_fence() -> None:
    text = "```json\n{\"actions\": []}\n```"
    assert _parse_action_json(text) == {"actions": []}


def test_parse_action_with_prose_around_json() -> None:
    text = 'Hier mein Plan:\n{"actions": [{"component": "a", "setpoint_mw": 2}]}\nFertig.'
    assert _parse_action_json(text) == {
        "actions": [{"component": "a", "setpoint_mw": 2}]
    }


def test_parse_action_invalid_returns_empty_actions() -> None:
    assert _parse_action_json("kein json hier") == {"actions": []}
    assert _parse_action_json("{kaputt}") == {"actions": []}


# ---------------------------------------------------------------------------
# AnthropicAIController — nur testen wenn API-Key + Paket vorhanden
# ---------------------------------------------------------------------------

def test_anthropic_controller_requires_api_key(monkeypatch) -> None:
    """Ohne API-Key muss die Initialisierung mit klarer Meldung scheitern."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    try:
        import anthropic  # type: ignore  # noqa: F401
    except ImportError:
        pytest.skip("anthropic-Paket nicht installiert")
    with pytest.raises(RuntimeError, match="API-Key"):
        AnthropicAIController()
