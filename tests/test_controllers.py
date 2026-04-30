"""Controller-Tests + erste Vergleichszahlen Naive vs. RuleBased.

Diese Tests dokumentieren auch die wesentlichen Vergleichsaussagen, die
spaeter in der Seminararbeit auftauchen werden (CO2-Reduktion, Reduktion
von Energieverschwendung, verbleibende Schwaechen der Heuristik).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sgsim.components import (
    BiomassPlant,
    CoalPlant,
    GasGuDPlant,
    Storage,
)
from sgsim.controllers import NaiveController
from sgsim.experiment import _next_ctx, build_grid, run_experiment


SCENARIO = Path(__file__).parent.parent / "src" / "sgsim" / "scenarios" / "stadt_mittel.yaml"


def test_naive_initialize_sets_constant_setpoints() -> None:
    grid = build_grid(SCENARIO, seed=42)
    NaiveController().initialize(grid)
    for c in grid.components:
        if isinstance(c, CoalPlant):
            assert c.setpoint_mw == pytest.approx(c.p_max_mw * 0.60)
        elif isinstance(c, GasGuDPlant):
            assert c.setpoint_mw == pytest.approx(c.p_max_mw * 0.40)
        elif isinstance(c, BiomassPlant):
            assert c.setpoint_mw == pytest.approx(c.p_max_mw)
        elif isinstance(c, Storage):
            assert c.setpoint_mw == 0.0


def test_naive_does_not_change_setpoints_after_step() -> None:
    grid = build_grid(SCENARIO, seed=42)
    ctrl = NaiveController()
    ctrl.initialize(grid)
    coal = next(c for c in grid.components if isinstance(c, CoalPlant))
    setpoint_before = coal.setpoint_mw
    grid.tick()
    ctrl.step(grid, _next_ctx(grid))
    assert coal.setpoint_mw == setpoint_before


# ---------------------------------------------------------------------------
# Vergleichende Aussagen Naive vs. RuleBased
# ---------------------------------------------------------------------------

def _runs() -> tuple[dict, dict]:
    g_naive, _ = run_experiment(SCENARIO, "naive", steps=96, seed=42)
    g_rb, _ = run_experiment(SCENARIO, "rule_based", steps=96, seed=42)
    return g_naive.metrics(), g_rb.metrics()


def test_rule_based_yields_lower_co2_than_naive() -> None:
    """Hauptthese: regelbasierte Steuerung emittiert weniger CO2."""
    m_naive, m_rb = _runs()
    assert m_rb["co2_kg"] < m_naive["co2_kg"]
    # Mindestens 30 % CO2-Reduktion erwartet
    reduction = (m_naive["co2_kg"] - m_rb["co2_kg"]) / m_naive["co2_kg"]
    assert reduction > 0.30, f"Nur {reduction:.1%} CO2-Reduktion"


def test_rule_based_dramatically_less_surplus() -> None:
    """RuleBased verschwendet drastisch weniger Energie als naive Steuerung."""
    m_naive, m_rb = _runs()
    # Naive ueberproduziert massiv (Surplus > 50 % des Bedarfs erwartet)
    assert m_naive["surplus_energy_mwh"] > m_naive["energy_consumed_mwh"] * 0.5
    # RuleBased mindestens 80 % weniger Surplus als naive
    assert m_rb["surplus_energy_mwh"] < m_naive["surplus_energy_mwh"] * 0.2


def test_rule_based_brownouts_below_threshold() -> None:
    """RuleBased erleidet einige Brownouts (Heuristik-Schwaeche, Kohle-Traegheit),
    aber unter 30 % der Zeitschritte. Genau dieser Spielraum ist der Hebel
    fuer die spaetere KI-Verbesserung.
    """
    _, m_rb = _runs()
    assert m_rb["brownout_steps"] < 30  # < ~31 % von 96 Ticks


def test_rule_based_uses_storage() -> None:
    """Speicher muss tatsaechlich beladen/entladen werden."""
    grid, _ = run_experiment(SCENARIO, "rule_based", steps=96, seed=42)
    soc_series = []
    for r in grid.history:
        det = r.component_details.get("batterie_quartier", {})
        if "soc_mwh" in det:
            soc_series.append(det["soc_mwh"])
    assert max(soc_series) - min(soc_series) > 1.0


def test_rule_based_curtails_or_absorbs_surplus() -> None:
    """Bei rule_based muss entweder Curtailment > 0 oder Speicher-Aufnahme
    sichtbar sein — sonst ginge der Ueberschuss aus der Kohle-Mindestlast
    nirgends hin und gaebe es 0 Surplus, was unrealistisch waere."""
    grid, _ = run_experiment(SCENARIO, "rule_based", steps=96, seed=42)
    saw_curtailment = False
    saw_charge = False
    for r in grid.history:
        if r.component_details.get("pv_aufdach", {}).get("curtailment", 0.0) > 0.0:
            saw_curtailment = True
        if r.components.get("batterie_quartier", 0.0) < -0.1:
            saw_charge = True
        if r.components.get("pumpspeicher_alpental", 0.0) < -0.1:
            saw_charge = True
    assert saw_curtailment or saw_charge


def test_compare_runs_returns_deltas() -> None:
    """compare_runs liefert prozentuale Differenzen zur Baseline."""
    from sgsim.experiment import compare_runs, export_csv, write_metrics_sidecar
    import tempfile

    g_naive, _ = run_experiment(SCENARIO, "naive", steps=48, seed=42)
    g_rb, _ = run_experiment(SCENARIO, "rule_based", steps=48, seed=42)

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        p1 = td_path / "naive.csv"
        p2 = td_path / "rb.csv"
        export_csv(g_naive, p1)
        export_csv(g_rb, p2)
        write_metrics_sidecar(g_naive, p1, "naive")
        write_metrics_sidecar(g_rb, p2, "rule_based")
        result = compare_runs([p1, p2])

    assert result["baseline"]["controller"] == "naive"
    delta_co2 = result["deltas_vs_baseline_pct"][0]["co2_kg_pct"]
    assert delta_co2 < 0  # CO2-Reduktion ist negativ
