"""Phase-5-Tests: Reproducibility-Hash, Wirtschaftlichkeit, Property-Tests,
Trennung Last/Speicher-Buchhaltung."""

from __future__ import annotations

from pathlib import Path

import pytest

from sgsim.economics import EconomicsParams, compute_economics
from sgsim.experiment import (
    build_grid,
    reproducibility_hash,
    run_experiment,
)


SCENARIO = Path(__file__).parent.parent / "src" / "sgsim" / "scenarios" / "stadt_mittel.yaml"


# ---------------------------------------------------------------------------
# Reproducibility-Hash
# ---------------------------------------------------------------------------

def test_repro_hash_identical_for_same_inputs() -> None:
    h1 = reproducibility_hash(SCENARIO, seed=42, controller_name="rule_based", steps=96)
    h2 = reproducibility_hash(SCENARIO, seed=42, controller_name="rule_based", steps=96)
    assert h1 == h2


def test_repro_hash_changes_with_seed() -> None:
    h1 = reproducibility_hash(SCENARIO, seed=42, controller_name="rule_based", steps=96)
    h2 = reproducibility_hash(SCENARIO, seed=43, controller_name="rule_based", steps=96)
    assert h1 != h2


def test_repro_hash_changes_with_controller() -> None:
    h1 = reproducibility_hash(SCENARIO, seed=42, controller_name="rule_based", steps=96)
    h2 = reproducibility_hash(SCENARIO, seed=42, controller_name="naive", steps=96)
    assert h1 != h2


def test_repro_hash_short_format() -> None:
    h = reproducibility_hash(SCENARIO, seed=42, controller_name="naive", steps=96)
    assert len(h) == 16
    int(h, 16)  # gueltige Hex


# ---------------------------------------------------------------------------
# Wirtschaftlichkeit
# ---------------------------------------------------------------------------

def test_economics_keys_present() -> None:
    grid, _ = run_experiment(SCENARIO, "rule_based", steps=96, seed=42)
    e = compute_economics(grid)
    for k in ("fuel_cost_eur", "co2_cost_eur", "storage_cost_eur",
              "voll_cost_eur", "total_cost_eur", "market_revenue_eur",
              "net_eur", "lcoe_eur_per_mwh"):
        assert k in e


def test_economics_voll_dominates_with_brownouts() -> None:
    """In einem Lauf mit Brownouts dominieren die VOLL-Kosten, weil der
    EUR/MWh-Faktor sehr hoch ist (7000 EUR/MWh)."""
    grid, _ = run_experiment(SCENARIO, "rule_based", steps=96, seed=42)
    e = compute_economics(grid)
    if grid.metrics()["brownout_steps"] > 0:
        assert e["voll_cost_eur"] > 0


def test_economics_custom_params_override() -> None:
    grid, _ = run_experiment(SCENARIO, "naive", steps=24, seed=42)
    cheap = compute_economics(grid, EconomicsParams(co2_price_eur_per_t=0.0))
    normal = compute_economics(grid)
    assert cheap["co2_cost_eur"] == 0.0
    assert normal["co2_cost_eur"] >= 0.0


# ---------------------------------------------------------------------------
# Energie-Buchhaltung getrennt
# ---------------------------------------------------------------------------

def test_load_energy_separated_from_storage_charge() -> None:
    """Die getrennten Felder muessen einzeln korrekt sein und die Summe
    plus Sektorkopplungs-Ansicht muss hoechstens energy_out_mwh ergeben."""
    grid, _ = run_experiment(SCENARIO, "rule_based", steps=96, seed=42)
    total_load = sum(r.load_energy_mwh for r in grid.history)
    total_storage_charge = sum(r.storage_charge_mwh for r in grid.history)
    total_out = sum(r.energy_out_mwh for r in grid.history)
    assert total_load > 0
    # storage_charge_mwh kann 0 sein, wenn nie geladen wurde
    assert total_storage_charge >= 0
    # Last + Speicherladen <= Gesamtbezug (Rest = Sektorkopplungs-Lasten)
    assert total_load + total_storage_charge <= total_out + 1e-6


# ---------------------------------------------------------------------------
# Property-basierte Tests (ohne externe Dependency, eigene Loop)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", [1, 7, 13, 42, 99, 200])
def test_energy_balance_holds_for_any_seed(seed: int) -> None:
    """Property: fuer JEDEN Seed muss die Bilanz exakt schliessen.

    energy_in - energy_out == imbalance_total (innerhalb numerischer
    Toleranz). Das ist ein fundamentales Buchhaltungs-Invariant der Engine.
    """
    grid = build_grid(SCENARIO, seed=seed)
    grid.run(96)
    e_in = sum(r.energy_in_mwh for r in grid.history)
    e_out = sum(r.energy_out_mwh for r in grid.history)
    net = sum(r.imbalance_mwh for r in grid.history)
    assert (e_in - e_out) == pytest.approx(net, rel=1e-9, abs=1e-9)


@pytest.mark.parametrize("seed", [1, 7, 13, 42, 99, 200])
def test_co2_nonnegative_for_any_seed(seed: int) -> None:
    """Property: CO2 ist nie negativ (kein Erzeuger 'verbraucht' CO2)."""
    grid = build_grid(SCENARIO, seed=seed)
    grid.run(96)
    for r in grid.history:
        assert r.co2_kg >= 0.0


@pytest.mark.parametrize("seed", [1, 42, 99])
def test_storage_soc_within_bounds(seed: int) -> None:
    """Property: SoC eines Speichers darf nie unter min_soc oder ueber capacity."""
    from sgsim.components import Storage
    grid = build_grid(SCENARIO, seed=seed)
    grid.run(96)
    for c in grid.components:
        if isinstance(c, Storage):
            assert c.min_soc_mwh - 1e-6 <= c.soc_mwh <= c.capacity_mwh + 1e-6


def test_h2_turbine_consumes_hydrogen_storage() -> None:
    from sgsim.components import HydrogenGasTurbine, HydrogenStorage, ResidentialLoad
    from sgsim.engine import Grid
    from sgsim.weather import SyntheticWeather

    h2 = HydrogenStorage(
        name="h2",
        capacity_mwh=1000.0,
        soc_mwh=100.0,
        min_soc_mwh=10.0,
        p_max_charge_mw=100.0,
        p_max_discharge_mw=100.0,
    )
    turbine = HydrogenGasTurbine(name="h2_gt", setpoint_mw=40.0, current_p_mw=40.0)
    grid = Grid(
        components=[
            turbine,
            h2,
            ResidentialLoad(name="load", base_mw=1.0, peak_mw=0.0),
        ],
        weather=SyntheticWeather(seed=1),
    )
    before = h2.soc_mwh
    rec = grid.tick()
    assert rec.components["h2_gt"] > 0.0
    assert h2.soc_mwh < before


def test_h2_turbine_limited_by_empty_hydrogen_storage() -> None:
    from sgsim.components import HydrogenGasTurbine, HydrogenStorage
    from sgsim.engine import Grid
    from sgsim.weather import SyntheticWeather

    h2 = HydrogenStorage(
        name="h2",
        capacity_mwh=1000.0,
        soc_mwh=10.0,
        min_soc_mwh=10.0,
        p_max_charge_mw=100.0,
        p_max_discharge_mw=100.0,
    )
    turbine = HydrogenGasTurbine(name="h2_gt", setpoint_mw=100.0, current_p_mw=100.0)
    grid = Grid(components=[turbine, h2], weather=SyntheticWeather(seed=1))
    rec = grid.tick()
    assert rec.components["h2_gt"] == pytest.approx(0.0)


def test_electrolyzer_charges_hydrogen_storage() -> None:
    from sgsim.components import Electrolyzer, HydrogenStorage
    from sgsim.engine import Grid
    from sgsim.weather import SyntheticWeather

    h2 = HydrogenStorage(
        name="h2",
        capacity_mwh=1000.0,
        soc_mwh=100.0,
        min_soc_mwh=10.0,
        p_max_charge_mw=100.0,
        p_max_discharge_mw=100.0,
    )
    el = Electrolyzer(name="el", p_max_mw=50.0, eta_h2=0.70, setpoint_mw=20.0)
    grid = Grid(components=[el, h2], weather=SyntheticWeather(seed=1))
    before = h2.soc_mwh
    rec = grid.tick()
    assert rec.components["el"] == pytest.approx(-20.0)
    assert h2.soc_mwh == pytest.approx(before + 20.0 * 0.70 * grid.dt_h)


@pytest.mark.parametrize("seed", [1, 42])
def test_frequency_bounded_for_any_seed(seed: int) -> None:
    """Property: Frequenz bleibt im Cap-Bereich [49.0, 51.0]."""
    grid = build_grid(SCENARIO, seed=seed)
    grid.run(96)
    for r in grid.history:
        assert 49.0 <= r.frequency_hz <= 51.0
