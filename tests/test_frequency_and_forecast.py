"""Tests fuer Frequenzmodell, Forecast-Rauschen und CSV-Loader."""

from __future__ import annotations

import csv
import random
from pathlib import Path

import pytest

from sgsim.components import TickContext
from sgsim.data_loaders import CsvProfileLoad, CsvWeather
from sgsim.forecast import noisy_forecast
from sgsim.frequency import F_NOMINAL_HZ, FrequencyState


# ---------------------------------------------------------------------------
# Frequenz
# ---------------------------------------------------------------------------

def test_frequency_starts_at_nominal() -> None:
    f = FrequencyState()
    assert f.f_hz == F_NOMINAL_HZ
    assert not f.is_outside_dead_band()


def test_frequency_drops_under_load() -> None:
    """Bei P_total<0 (mehr Last als Erzeugung) muss die Frequenz fallen."""
    f = FrequencyState(inertia_h_s=5.0, s_base_mw=500.0)
    initial = f.f_hz
    # 50 MW Defizit ueber 1 s
    f.step(p_total_mw=-50.0, dt_s=1.0)
    assert f.f_hz < initial


def test_frequency_recovers_with_decay() -> None:
    """Ohne fortgesetztes Defizit driftet die Frequenz Richtung 50 Hz."""
    f = FrequencyState()
    f.f_hz = 49.5
    for _ in range(50):
        f.step(p_total_mw=0.0, dt_s=1.0)
    assert abs(f.f_hz - F_NOMINAL_HZ) < 0.5


def test_frequency_capped() -> None:
    """Frequenz darf physikalisch nicht beliebig wegrennen."""
    f = FrequencyState()
    for _ in range(1000):
        f.step(p_total_mw=-1000.0, dt_s=1.0)
    assert f.f_hz >= F_NOMINAL_HZ - 2.0


def test_frequency_dead_band_check() -> None:
    f = FrequencyState()
    f.f_hz = 50.1
    assert not f.is_outside_dead_band()
    f.f_hz = 50.3
    assert f.is_outside_dead_band()


# ---------------------------------------------------------------------------
# Forecast-Rauschen
# ---------------------------------------------------------------------------

def test_noisy_forecast_close_to_truth_at_short_horizon() -> None:
    rng = random.Random(0)
    ctx = TickContext(
        sim_time_h=12.0, hour_of_day=12.0,
        irradiance_w_m2=500.0, wind_speed_m_s=8.0, temperature_c=10.0,
    )
    n = 200
    irr_diffs = []
    for _ in range(n):
        f = noisy_forecast(ctx, horizon_h=0.25, rng=rng)
        irr_diffs.append(f.irradiance_w_m2 - 500.0)
    mean_diff = sum(irr_diffs) / n
    # Mittelwert nahe Null
    assert abs(mean_diff) < 50.0


def test_noisy_forecast_increases_with_horizon() -> None:
    rng = random.Random(0)
    ctx = TickContext(
        sim_time_h=12.0, hour_of_day=12.0,
        irradiance_w_m2=500.0, wind_speed_m_s=8.0, temperature_c=10.0,
    )

    def std(samples):
        m = sum(samples) / len(samples)
        return (sum((x - m) ** 2 for x in samples) / len(samples)) ** 0.5

    short = [noisy_forecast(ctx, horizon_h=0.25, rng=rng).irradiance_w_m2
             for _ in range(200)]
    long = [noisy_forecast(ctx, horizon_h=4.0, rng=rng).irradiance_w_m2
            for _ in range(200)]
    assert std(long) > std(short)


def test_noisy_forecast_clamps_to_nonnegative() -> None:
    rng = random.Random(0)
    ctx = TickContext(
        sim_time_h=0.0, hour_of_day=0.0,
        irradiance_w_m2=10.0, wind_speed_m_s=1.0, temperature_c=-5.0,
    )
    for _ in range(1000):
        f = noisy_forecast(ctx, horizon_h=2.0, rng=rng)
        assert f.irradiance_w_m2 >= 0.0
        assert f.wind_speed_m_s >= 0.0


# ---------------------------------------------------------------------------
# CSV-Profile-Last
# ---------------------------------------------------------------------------

def test_csv_profile_load_interpolates(tmp_path: Path) -> None:
    csv_path = tmp_path / "h0.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["hour_of_day", "relative_load"])
        w.writerow([0, 0.4])
        w.writerow([12, 1.0])
        w.writerow([23, 0.5])

    load = CsvProfileLoad(name="csvload", csv_path=str(csv_path), peak_mw=100.0)
    ctx_noon = TickContext(sim_time_h=12.0, hour_of_day=12.0,
                            irradiance_w_m2=0, wind_speed_m_s=0, temperature_c=10)
    p = load.step(0.25, ctx_noon)
    assert p == pytest.approx(-100.0)  # Peak ist 100 MW


def test_csv_profile_falls_back_when_no_path() -> None:
    """Ohne csv_path liefert die Komponente 0."""
    load = CsvProfileLoad(name="empty", csv_path="", peak_mw=100.0)
    ctx = TickContext(sim_time_h=0, hour_of_day=0,
                       irradiance_w_m2=0, wind_speed_m_s=0, temperature_c=10)
    assert load.step(0.25, ctx) == 0.0


# ---------------------------------------------------------------------------
# CSV-Wetter
# ---------------------------------------------------------------------------

def test_csv_weather_returns_csv_values(tmp_path: Path) -> None:
    csv_path = tmp_path / "weather.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["hour_of_year", "irradiance_w_m2", "wind_m_s", "temperature_c"])
        w.writerow([0, 300, 5.5, 8.0])
        w.writerow([1, 600, 6.0, 9.0])

    weather = CsvWeather(seed=0, csv_path=str(csv_path))
    assert weather.irradiance(0.0) == 300.0
    assert weather.irradiance(1.0) == 600.0
    assert weather.wind_speed(0.0) == 5.5
    assert weather.temperature(1.0) == 9.0


def test_csv_weather_falls_back_to_synthetic() -> None:
    """Ohne csv_path verhaelt sich CsvWeather wie SyntheticWeather."""
    weather = CsvWeather(seed=42, csv_path="")
    # Funktioniert wie SyntheticWeather (Sinusbogen → mittags > 0)
    assert weather.irradiance(12.0) > 0.0


# ---------------------------------------------------------------------------
# Engine integriert Frequenz korrekt
# ---------------------------------------------------------------------------

def test_engine_records_frequency() -> None:
    from sgsim.components import PVPlant, ResidentialLoad
    from sgsim.engine import Grid

    g = Grid(
        name="freq_test",
        components=[
            PVPlant(name="pv", area_m2=50_000),
            ResidentialLoad(name="last", base_mw=8.0, peak_mw=12.0),
        ],
    )
    g.tick()
    rec = g.history[-1]
    assert hasattr(rec, "frequency_hz")
    assert 48.0 < rec.frequency_hz < 52.0
    assert rec.frequency_deviation_hz >= 0.0
