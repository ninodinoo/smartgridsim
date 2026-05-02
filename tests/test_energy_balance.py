"""Physikalische Sanity-Checks der Engine.

Diese Tests sind die Grundlage dafuer, dass die spaeter exportierten
Messwerte fuer die Seminararbeit verlaesslich sind.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sgsim.components import PVPlant, ResidentialLoad
from sgsim.engine import Grid
from sgsim.weather import SyntheticWeather


def make_grid(seed: int = 42) -> Grid:
    return Grid(
        name="test",
        seed=seed,
        dt_min=15,
        components=[
            PVPlant(name="pv", area_m2=50_000),
            ResidentialLoad(name="last", base_mw=8.0, peak_mw=12.0),
        ],
        weather=SyntheticWeather(seed=seed),
    )


def test_tick_advances_time_by_dt() -> None:
    g = make_grid()
    g.tick()
    assert g.step_count == 1
    assert g.sim_time_h == pytest.approx(0.25)


def test_pv_zero_at_night() -> None:
    g = make_grid()
    g.sim_time_h = 2.0
    rec = g.tick()
    assert rec.components["pv"] == pytest.approx(0.0, abs=1e-9)


def test_pv_positive_at_noon() -> None:
    g = make_grid()
    g.sim_time_h = 12.0
    rec = g.tick()
    assert rec.components["pv"] > 1.0


def test_load_is_negative() -> None:
    g = make_grid()
    rec = g.tick()
    assert rec.components["last"] < 0.0


def test_imbalance_equals_p_total_times_dt() -> None:
    g = make_grid()
    rec = g.tick()
    assert rec.imbalance_mwh == pytest.approx(rec.p_total_mw * g.dt_h)


def test_energy_accounting_consistency_over_day() -> None:
    """Bilanz ueber 24 h: erzeugte - verbrauchte Energie = Netto-Imbalance."""
    g = make_grid()
    g.run(96)
    e_in = sum(r.energy_in_mwh for r in g.history)
    e_out = sum(r.energy_out_mwh for r in g.history)
    net = sum(r.imbalance_mwh for r in g.history)
    assert (e_in - e_out) == pytest.approx(net, rel=1e-9, abs=1e-9)


def test_state_round_trip(tmp_path: Path) -> None:
    g = make_grid()
    g.run(10)
    f = tmp_path / "state.json"
    g.save(f)
    g2 = Grid.load(f)
    assert g2.step_count == g.step_count
    assert g2.sim_time_h == pytest.approx(g.sim_time_h)
    assert [c.name for c in g2.components] == [c.name for c in g.components]
    g.tick()
    g2.tick()
    assert g.history[-1].p_total_mw == pytest.approx(g2.history[-1].p_total_mw)


def test_weather_calls_are_idempotent() -> None:
    w = SyntheticWeather(seed=123)
    assert w.irradiance(12.0) == pytest.approx(w.irradiance(12.0))
    assert w.wind_speed(12.0) == pytest.approx(w.wind_speed(12.0))


def test_extra_weather_reads_do_not_change_next_tick() -> None:
    g1 = make_grid(seed=123)
    g2 = make_grid(seed=123)
    _ = g2.weather.irradiance(0.0)
    _ = g2.weather.wind_speed(0.0)
    r1 = g1.tick()
    r2 = g2.tick()
    assert r2.irradiance == pytest.approx(r1.irradiance)
    assert r2.wind == pytest.approx(r1.wind)


def test_curtailment_reduces_pv() -> None:
    g = make_grid()
    g.sim_time_h = 12.0
    rec_full = g.tick()

    g2 = make_grid()
    pv = next(c for c in g2.components if c.name == "pv")
    pv.curtailment = 0.5
    g2.sim_time_h = 12.0
    rec_half = g2.tick()

    assert rec_half.components["pv"] == pytest.approx(
        rec_full.components["pv"] * 0.5, rel=1e-6
    )
