"""Physikalische Plausibilitaetstests fuer einzelne Komponenten."""

from __future__ import annotations

import math

import pytest

from sgsim.components import (
    BatteryStorage,
    BiomassPlant,
    CoalPlant,
    CommercialLoad,
    GasGuDPlant,
    HydrogenStorage,
    IndustrialLoad,
    PumpedHydroStorage,
    RunOfRiverHydro,
    TickContext,
    WindTurbine,
    from_dict,
)


def _ctx(wind: float = 0.0, irrad: float = 0.0, hour: float = 12.0) -> TickContext:
    return TickContext(
        sim_time_h=hour,
        hour_of_day=hour,
        irradiance_w_m2=irrad,
        wind_speed_m_s=wind,
        temperature_c=10.0,
    )


# ---------------------------------------------------------------------------
# Wind
# ---------------------------------------------------------------------------

def test_wind_zero_below_cut_in() -> None:
    w = WindTurbine(name="w", rotor_diameter_m=120, p_rated_mw=3.0, n_turbines=5)
    assert w.step(0.25, _ctx(wind=2.0)) == 0.0


def test_wind_zero_above_cut_out() -> None:
    w = WindTurbine(name="w", rotor_diameter_m=120, p_rated_mw=3.0, n_turbines=5)
    assert w.step(0.25, _ctx(wind=30.0)) == 0.0


def test_wind_capped_at_rated() -> None:
    w = WindTurbine(name="w", rotor_diameter_m=120, p_rated_mw=3.0, n_turbines=5)
    p = w.step(0.25, _ctx(wind=15.0))
    # bei v_rated <= v < v_cut_out genau n * P_rated
    assert p == pytest.approx(15.0, rel=1e-6)


def test_wind_below_betz_limit() -> None:
    """c_p darf physikalisch das Betz-Limit 16/27 nicht uebersteigen."""
    w = WindTurbine(name="w", rotor_diameter_m=120, p_rated_mw=10.0, n_turbines=1)
    assert w.cp < 16.0 / 27.0


def test_wind_cubic_in_partial_load() -> None:
    """Im Teillastbereich skaliert P mit v^3 (vor Cap)."""
    w = WindTurbine(name="w", rotor_diameter_m=120, p_rated_mw=100.0,
                    n_turbines=1, v_rated=30.0, v_cut_out=40.0)
    p1 = w.step(0.25, _ctx(wind=5.0))
    p2 = w.step(0.25, _ctx(wind=10.0))
    assert p2 / p1 == pytest.approx(8.0, rel=0.01)  # (10/5)^3


# ---------------------------------------------------------------------------
# Lasten
# ---------------------------------------------------------------------------

def test_commercial_load_zero_at_night() -> None:
    c = CommercialLoad(name="c", base_mw=5.0, peak_mw=20.0)
    assert c.step(0.25, _ctx(hour=3.0)) == pytest.approx(-5.0)


def test_industrial_load_constant_with_night_reduction() -> None:
    i = IndustrialLoad(name="i", base_mw=100.0, night_reduction=0.2)
    assert i.step(0.25, _ctx(hour=12.0)) == pytest.approx(-100.0)
    assert i.step(0.25, _ctx(hour=2.0)) == pytest.approx(-80.0)


# ---------------------------------------------------------------------------
# Run-of-river
# ---------------------------------------------------------------------------

def test_runofriver_constant_with_availability() -> None:
    r = RunOfRiverHydro(name="r", p_mw=10.0, availability=0.9)
    assert r.step(0.25, _ctx()) == pytest.approx(9.0)


# ---------------------------------------------------------------------------
# Dispatchierbar
# ---------------------------------------------------------------------------

def test_dispatch_respects_ramp() -> None:
    g = GasGuDPlant(name="g", p_min_mw=50.0, p_max_mw=400.0,
                    ramp_mw_per_min=10.0, eta=0.58, co2_kg_per_mwh=350.0)
    g.setpoint_mw = 400.0
    p1 = g.step(0.25, _ctx())  # dt = 15 min, max ΔP = 150 MW
    # In erstem Tick darf nicht mehr als 150 MW erreicht werden
    assert p1 <= 150.0 + 1e-9


def test_dispatch_ramps_up_over_multiple_ticks() -> None:
    g = GasGuDPlant(name="g")
    g.setpoint_mw = 250.0
    powers = [g.step(0.25, _ctx()) for _ in range(5)]
    assert powers == sorted(powers)             # monoton steigend
    assert powers[-1] == pytest.approx(250.0, abs=1.0)


def test_dispatch_caps_at_p_max() -> None:
    g = CoalPlant(name="k")
    g.setpoint_mw = 9999.0
    for _ in range(200):
        p = g.step(0.25, _ctx())
    assert p == pytest.approx(g.p_max_mw)


def test_dispatch_zero_setpoint_off() -> None:
    g = BiomassPlant(name="b")
    g.setpoint_mw = 0.0
    assert g.step(0.25, _ctx()) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Speicher
# ---------------------------------------------------------------------------

def test_battery_charge_discharge_round_trip() -> None:
    b = BatteryStorage(name="b", capacity_mwh=100.0, soc_mwh=50.0,
                       p_max_charge_mw=20.0, p_max_discharge_mw=20.0,
                       eta_charge=0.95, eta_discharge=0.95)
    # 1 h laden mit 10 MW → SoC steigt um 10 * 0.95 = 9.5 MWh
    b.setpoint_mw = -10.0
    p = b.step(1.0, _ctx())
    assert p == pytest.approx(-10.0)
    assert b.soc_mwh == pytest.approx(50.0 + 9.5)

    # 1 h entladen mit 10 MW → SoC sinkt um 10 / 0.95 = 10.526 MWh
    b.setpoint_mw = 10.0
    p = b.step(1.0, _ctx())
    assert p == pytest.approx(10.0)
    assert b.soc_mwh == pytest.approx(50.0 + 9.5 - 10.0 / 0.95, rel=1e-6)


def test_battery_cannot_overcharge() -> None:
    b = BatteryStorage(name="b", capacity_mwh=100.0, soc_mwh=99.0,
                       p_max_charge_mw=50.0, p_max_discharge_mw=50.0)
    b.setpoint_mw = -50.0
    p = b.step(1.0, _ctx())
    assert b.soc_mwh <= 100.0 + 1e-9
    # Tatsaechlich gelieferte Ladeleistung kleiner als Setpoint
    assert -p < 50.0


def test_battery_cannot_overdischarge() -> None:
    b = BatteryStorage(name="b", capacity_mwh=100.0, soc_mwh=5.0,
                       p_max_charge_mw=50.0, p_max_discharge_mw=50.0,
                       min_soc_mwh=0.0)
    b.setpoint_mw = 50.0
    p = b.step(1.0, _ctx())
    assert b.soc_mwh >= -1e-9
    assert p < 50.0


def test_pumped_hydro_capacity_from_geometry() -> None:
    """E = rho * V * g * h. 1000 * 1_000_000 * 9.81 * 100 / 3.6e9 ≈ 272.5 MWh."""
    psw = PumpedHydroStorage.from_geometry(
        name="psw",
        head_m=100.0,
        upper_volume_m3=1_000_000,
        p_max_charge_mw=100.0,
        p_max_discharge_mw=100.0,
    )
    expected = 1000.0 * 1_000_000 * 9.81 * 100.0 / 3.6e9
    assert psw.capacity_mwh == pytest.approx(expected, rel=1e-9)
    assert psw.soc_mwh == pytest.approx(expected * 0.5)


def test_pumped_hydro_round_trip_efficiency() -> None:
    psw = PumpedHydroStorage.from_geometry(
        name="psw",
        head_m=200.0,
        upper_volume_m3=2_000_000,
        p_max_charge_mw=100.0,
        p_max_discharge_mw=100.0,
        initial_fill=0.5,
    )
    # 1 h laden mit 100 MW → 100 * 0.88 = 88 MWh ins Becken
    soc0 = psw.soc_mwh
    psw.setpoint_mw = -100.0
    psw.step(1.0, _ctx())
    assert psw.soc_mwh - soc0 == pytest.approx(88.0, rel=1e-6)
    # 1 h entladen mit 100 MW → 100 / 0.91 ≈ 109.89 MWh aus Becken
    soc1 = psw.soc_mwh
    psw.setpoint_mw = 100.0
    psw.step(1.0, _ctx())
    assert soc1 - psw.soc_mwh == pytest.approx(100.0 / 0.91, rel=1e-6)


def test_hydrogen_round_trip_below_battery() -> None:
    """H2-Round-Trip muss deutlich unter dem von Li-Ion liegen."""
    h = HydrogenStorage(name="h", capacity_mwh=1000.0, soc_mwh=500.0,
                        p_max_charge_mw=10.0, p_max_discharge_mw=10.0)
    rt = h.eta_charge * h.eta_discharge
    assert rt < 0.45                # typisch 0.3..0.4


# ---------------------------------------------------------------------------
# Serialisierung neuer Typen
# ---------------------------------------------------------------------------

def test_round_trip_serialization_all_types() -> None:
    cases = [
        WindTurbine(name="w", rotor_diameter_m=130, p_rated_mw=4.0, n_turbines=3),
        GasGuDPlant(name="g"),
        CoalPlant(name="k"),
        BiomassPlant(name="b"),
        BatteryStorage(name="bat", capacity_mwh=50.0, soc_mwh=20.0,
                       p_max_charge_mw=10.0, p_max_discharge_mw=10.0),
        RunOfRiverHydro(name="r", p_mw=5.0),
    ]
    for c in cases:
        d = c.to_dict()
        c2 = from_dict(d)
        assert type(c2) is type(c)
        assert c2.name == c.name


def test_pumped_hydro_from_geometry_yaml() -> None:
    d = {
        "type": "PumpedHydroStorage",
        "name": "psw",
        "head_m": 200.0,
        "upper_volume_m3": 1_800_000,
        "p_max_charge_mw": 200.0,
        "p_max_discharge_mw": 220.0,
        "initial_fill": 0.5,
    }
    psw = from_dict(d)
    assert isinstance(psw, PumpedHydroStorage)
    assert psw.capacity_mwh > 0
