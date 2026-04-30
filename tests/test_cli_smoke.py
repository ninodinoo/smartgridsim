"""End-to-End-Smoke-Test der CLI: init -> run -> metrics -> export."""

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
    assert "pv_dachanlagen" in payload["components"]
    assert (tmp_path / ".sgsim_state.json").exists()

    p = _run(["tick"], tmp_path)
    assert p.returncode == 0, p.stderr
    rec = json.loads(p.stdout)
    assert rec["step"] == 0

    p = _run(["run", "--steps", "95"], tmp_path)
    assert p.returncode == 0, p.stderr
    payload = json.loads(p.stdout)
    assert payload["step_count"] == 96  # 1 + 95

    p = _run(["metrics"], tmp_path)
    assert p.returncode == 0, p.stderr
    metrics = json.loads(p.stdout)
    assert metrics["steps"] == 96
    assert metrics["energy_consumed_mwh"] > 0
    assert metrics["energy_generated_mwh"] > 0

    out_csv = tmp_path / "out.csv"
    p = _run(["export", "--out", str(out_csv)], tmp_path)
    assert p.returncode == 0, p.stderr
    assert out_csv.exists()
    lines = out_csv.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 97  # Header + 96 Zeilen


def test_curtailment_command(tmp_path: Path) -> None:
    _run(["init"], tmp_path)
    p = _run(["set-curtailment", "pv_dachanlagen", "0.4"], tmp_path)
    assert p.returncode == 0, p.stderr
    payload = json.loads(p.stdout)
    assert payload["curtailment"] == 0.4
