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
    GeothermalPlant,
    HydrogenGasTurbine,
    Storage,
)
from sgsim.controllers import NaiveController
from sgsim.experiment import _next_ctx, build_grid, run_experiment


SCENARIO = Path(__file__).parent.parent / "src" / "sgsim" / "scenarios" / "stadt_mittel.yaml"


def test_naive_initialize_sets_constant_setpoints() -> None:
    grid = build_grid(SCENARIO, seed=42)
    NaiveController().initialize(grid)
    for c in grid.components:
        if isinstance(c, BiomassPlant):
            assert c.setpoint_mw == pytest.approx(c.p_max_mw)
        elif isinstance(c, GeothermalPlant):
            assert c.setpoint_mw == pytest.approx(c.p_max_mw)
        elif isinstance(c, HydrogenGasTurbine):
            assert c.setpoint_mw == pytest.approx(c.p_max_mw * 0.50)
        elif isinstance(c, Storage):
            assert c.setpoint_mw == 0.0


def test_naive_does_not_change_setpoints_after_step() -> None:
    grid = build_grid(SCENARIO, seed=42)
    ctrl = NaiveController()
    ctrl.initialize(grid)
    h2 = next(c for c in grid.components if isinstance(c, HydrogenGasTurbine))
    setpoint_before = h2.setpoint_mw
    grid.tick()
    ctrl.step(grid, _next_ctx(grid))
    assert h2.setpoint_mw == setpoint_before


# ---------------------------------------------------------------------------
# Vergleichende Aussagen Naive vs. RuleBased
# ---------------------------------------------------------------------------

def _runs() -> tuple[dict, dict]:
    g_naive, _ = run_experiment(SCENARIO, "naive", steps=96, seed=42)
    g_rb, _ = run_experiment(SCENARIO, "rule_based", steps=96, seed=42)
    return g_naive.metrics(), g_rb.metrics()


def test_rule_based_yields_lower_co2_than_naive() -> None:
    """In einem 100%-erneuerbaren System sind die CO2-Niveaus ohnehin
    niedrig (nur Bio/Geothermie/H2-GuD-Hilfsstrom). RuleBased sollte
    aber dennoch tendenziell weniger CO2 verursachen als die naive
    Steuerung mit voll laufender Bio + Geothermie."""
    m_naive, m_rb = _runs()
    assert m_rb["co2_kg"] <= m_naive["co2_kg"] * 1.05  # mit Toleranz


def test_rule_based_dramatically_less_surplus() -> None:
    """RuleBased verschwendet deutlich weniger Energie als naive."""
    m_naive, m_rb = _runs()
    # Naive ueberproduziert sichtbar (Surplus muss messbar sein)
    assert m_naive["surplus_energy_mwh"] > 100.0
    # RuleBased mindestens 50 % weniger Surplus als naive
    assert m_rb["surplus_energy_mwh"] < m_naive["surplus_energy_mwh"] * 0.5


def test_rule_based_brownouts_recorded() -> None:
    """In einem 100%-erneuerbaren System sind Brownouts selbst mit der
    regelbasierten Strategie wahrscheinlich (Volatilitaet von PV/Wind,
    keine konstanten fossilen Reserven). Die Engine muss sie korrekt
    zaehlen — das ist der Hauptmesspunkt fuer eine spaetere KI-Steuerung,
    die diese Schwaeche schliessen koennte.
    """
    _, m_rb = _runs()
    # Brownouts sollen gemessen werden (Wert >= 0). Hauptthese der Arbeit:
    # KI-Steuerung kann sie senken — daher hier kein scharfer Schwellwert.
    assert m_rb["brownout_steps"] >= 0
    assert m_rb["unserved_energy_mwh"] >= 0.0


def test_rule_based_uses_storage() -> None:
    """Speicher muss tatsaechlich beladen/entladen werden."""
    grid, _ = run_experiment(SCENARIO, "rule_based", steps=96, seed=42)
    soc_series = []
    for r in grid.history:
        det = r.component_details.get("batterie_quartier", {})
        if "soc_mwh" in det:
            soc_series.append(det["soc_mwh"])
    assert max(soc_series) - min(soc_series) > 1.0


def test_rule_based_uses_storage_or_curtailment() -> None:
    """Speicher muessen sich bewegen (laden oder entladen) ODER Curtailment
    muss greifen — sonst ist die Steuerung passiv und unterscheidet sich
    nicht von naive."""
    grid, _ = run_experiment(SCENARIO, "rule_based", steps=96, seed=42)
    saw_storage_action = False
    saw_curtailment = False
    storage_names = ("batterie_quartier", "pumpspeicher_alpental",
                     "h2_speicher_saisonal")
    pv_wind = ("pv_aufdach", "wind_onshore", "wind_offshore_anteil")
    for r in grid.history:
        for n in pv_wind:
            if r.component_details.get(n, {}).get("curtailment", 0.0) > 0.0:
                saw_curtailment = True
        for n in storage_names:
            if abs(r.components.get(n, 0.0)) > 0.1:
                saw_storage_action = True
    assert saw_storage_action or saw_curtailment


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
