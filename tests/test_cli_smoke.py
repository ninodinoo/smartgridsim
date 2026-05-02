"""End-to-End-Smoke-Test der CLI: init -> dispatch -> run -> metrics -> export."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "sgsim.cli", *cmd],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return proc


def test_full_cli_flow(tmp_path: Path) -> None:
    p = _run(["init"], tmp_path)
    assert p.returncode == 0, p.stderr
    payload = json.loads(p.stdout)
    assert payload["ok"] is True
    names = [c["name"] for c in payload["components"]]
    assert "pv_aufdach" in names
    assert "wind_onshore" in names
    assert "h2_gasturbine" in names
    assert "pumpspeicher_alpental" in names
    assert "h2_speicher_saisonal" in names
    assert (tmp_path / ".sgsim_state.json").exists()

    # Sollwerte fuer dispatchierbare Komponenten setzen
    for name, mw in [("h2_gasturbine", 100.0), ("biomasse", 20.0),
                     ("geothermie", 5.0), ("batterie_quartier", 0.0)]:
        p = _run(["dispatch", name, str(mw)], tmp_path)
        assert p.returncode == 0, p.stderr

    p = _run(["tick"], tmp_path)
    assert p.returncode == 0, p.stderr
    rec = json.loads(p.stdout)
    assert rec["step"] == 0

    p = _run(["run", "--steps", "95"], tmp_path)
    assert p.returncode == 0, p.stderr
    payload = json.loads(p.stdout)
    assert payload["step_count"] == 96

    p = _run(["metrics"], tmp_path)
    assert p.returncode == 0, p.stderr
    metrics = json.loads(p.stdout)
    assert metrics["steps"] == 96
    assert metrics["energy_consumed_mwh"] > 0
    assert metrics["energy_generated_mwh"] > 0
    # 100%-erneuerbares Szenario — CO2 nur noch aus Bio/Geothermie/H2-GuD-Hilfsstrom
    assert 0.0 <= metrics["renewable_share_of_demand"] <= 1.0

    out_csv = tmp_path / "out.csv"
    p = _run(["export", "--out", str(out_csv)], tmp_path)
    assert p.returncode == 0, p.stderr
    assert out_csv.exists()
    lines = out_csv.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 97  # Header + 96 Zeilen
    header = lines[0]
    assert "co2_kg" in header
    assert "D_pumpspeicher_alpental_soc_mwh" in header


def test_curtailment_command(tmp_path: Path) -> None:
    _run(["init"], tmp_path)
    p = _run(["set-curtailment", "pv_aufdach", "0.4"], tmp_path)
    assert p.returncode == 0, p.stderr
    payload = json.loads(p.stdout)
    assert payload["curtailment"] == 0.4


def test_init_seed_also_sets_weather_seed(tmp_path: Path) -> None:
    p = _run(["init", "--seed", "123"], tmp_path)
    assert p.returncode == 0, p.stderr
    p = _run(["state", "--full"], tmp_path)
    payload = json.loads(p.stdout)
    assert payload["seed"] == 123
    assert payload["weather"]["seed"] == 123


def test_dispatch_to_storage_negative_means_charge(tmp_path: Path) -> None:
    _run(["init"], tmp_path)
    p = _run(["dispatch", "--", "batterie_quartier", "-30"], tmp_path)
    assert p.returncode == 0, p.stderr
    payload = json.loads(p.stdout)
    assert payload["setpoint_mw"] == -30.0
    assert payload["type"] == "BatteryStorage"
