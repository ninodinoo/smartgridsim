"""Aggregiert die Pilot-Subagent-Laeufe und stellt sie den Baselines gegenueber.

Erwartet:
  results/baselines/<naive|rule_based>_seed<N>.csv (+ .metrics.json)
  runs/seed_<NN>/result.metrics.json   (vom Subagent geschrieben)

Output: kompakte Vergleichstabelle pro Seed, Aggregat ueber Seeds.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path


def load_metrics(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def find_subagent_metrics(seed: int) -> dict | None:
    seed_dir = Path("runs") / f"seed_{seed:02d}"
    sidecar = seed_dir / "result.metrics.json"
    if sidecar.exists():
        return load_metrics(sidecar)
    csv = seed_dir / "result.csv"
    if csv.exists():
        # Sidecar fehlt — wir lesen den state, falls vorhanden
        state_file = seed_dir / ".sgsim_state.json"
        if state_file.exists():
            from sgsim.engine import Grid
            grid = Grid.load(state_file)
            return grid.metrics()
    return None


def fmt_row(label: str, m: dict) -> str:
    co2 = m.get("co2_kg", 0) / 1000.0
    bro = m.get("brownout_steps", 0)
    sur = m.get("surplus_energy_mwh", 0)
    uns = m.get("unserved_energy_mwh", 0)
    ren = m.get("renewable_share_of_demand", 0) * 100
    return f"  {label:<22} CO2={co2:6.2f} t  brownouts={bro:3d}  surplus={sur:6.1f} MWh  unserved={uns:6.1f} MWh  ren={ren:4.1f}%"


def main(seeds: list[int]) -> int:
    rows_per_seed: dict[int, dict[str, dict]] = {}
    missing = []
    for seed in seeds:
        seed_data = {}
        for ctrl in ("naive", "rule_based"):
            p = Path("results") / "baselines" / f"{ctrl}_seed{seed}.metrics.json"
            if not p.exists():
                missing.append(str(p))
                continue
            seed_data[ctrl] = load_metrics(p)
        sub = find_subagent_metrics(seed)
        if sub is None:
            missing.append(f"runs/seed_{seed:02d}/result.metrics.json")
        else:
            seed_data["claude_subagent"] = sub
        rows_per_seed[seed] = seed_data

    if missing:
        print("FEHLEND:", file=sys.stderr)
        for m in missing:
            print(f"  {m}", file=sys.stderr)

    print("=" * 100)
    print(f"Pilot-Vergleich ueber Seeds: {seeds}")
    print("=" * 100)

    for seed in seeds:
        print(f"\n--- Seed {seed} ---")
        d = rows_per_seed[seed]
        for ctrl in ("naive", "rule_based", "claude_subagent"):
            if ctrl in d:
                print(fmt_row(ctrl, d[ctrl]))

    # Aggregat
    print("\n" + "=" * 100)
    print("Aggregat (Mittelwert ± Stdabw. ueber Seeds)")
    print("=" * 100)
    metrics_keys = [
        ("co2_kg", "CO2 [t]", lambda x: x / 1000),
        ("brownout_steps", "Brownouts", lambda x: x),
        ("surplus_energy_mwh", "Surplus [MWh]", lambda x: x),
        ("unserved_energy_mwh", "Unserved [MWh]", lambda x: x),
        ("renewable_share_of_demand", "Ren-Share [%]", lambda x: x * 100),
    ]
    print(f"\n{'Metrik':<20} {'Naive':>20} {'RuleBased':>20} {'ClaudeSub':>20}")
    print("-" * 84)
    for key, label, conv in metrics_keys:
        per_ctrl = {}
        for ctrl in ("naive", "rule_based", "claude_subagent"):
            vals = [conv(rows_per_seed[s][ctrl][key])
                    for s in seeds
                    if ctrl in rows_per_seed[s]]
            if vals:
                if len(vals) > 1:
                    per_ctrl[ctrl] = (statistics.mean(vals), statistics.stdev(vals))
                else:
                    per_ctrl[ctrl] = (vals[0], 0.0)
            else:
                per_ctrl[ctrl] = (None, None)
        cells = []
        for ctrl in ("naive", "rule_based", "claude_subagent"):
            m, s = per_ctrl[ctrl]
            if m is None:
                cells.append("n/a")
            elif s is not None:
                cells.append(f"{m:8.2f} ± {s:6.2f}")
            else:
                cells.append(f"{m:8.2f}")
        print(f"{label:<20} {cells[0]:>20} {cells[1]:>20} {cells[2]:>20}")

    # Welch-t / Cohen's d (Claude vs RuleBased) — nur wenn n>=2
    if len(seeds) >= 2:
        print("\n" + "=" * 100)
        print("Welch-t und Cohen's d: claude_subagent vs. rule_based")
        print("=" * 100)
        for key, label, conv in metrics_keys[:3]:  # CO2, Brownouts, Surplus
            rb_vals = [conv(rows_per_seed[s]["rule_based"][key]) for s in seeds
                       if "rule_based" in rows_per_seed[s]]
            cl_vals = [conv(rows_per_seed[s]["claude_subagent"][key]) for s in seeds
                       if "claude_subagent" in rows_per_seed[s]]
            if len(rb_vals) < 2 or len(cl_vals) < 2:
                print(f"  {label}: n zu klein fuer t-Test (rb={len(rb_vals)}, cl={len(cl_vals)})")
                continue
            m1, m2 = statistics.mean(cl_vals), statistics.mean(rb_vals)
            s1 = statistics.stdev(cl_vals)
            s2 = statistics.stdev(rb_vals)
            n1, n2 = len(cl_vals), len(rb_vals)
            # Welch t
            se = (s1 ** 2 / n1 + s2 ** 2 / n2) ** 0.5 if (s1 + s2) > 0 else 1e-9
            t = (m1 - m2) / se if se > 0 else float('nan')
            # Cohen's d (pooled SD)
            sp = (((n1 - 1) * s1 ** 2 + (n2 - 1) * s2 ** 2) / (n1 + n2 - 2)) ** 0.5
            d = (m1 - m2) / sp if sp > 0 else float('nan')
            print(f"  {label}: claude={m1:.2f}, rb={m2:.2f}, t={t:+.2f}, Cohen's d={d:+.2f}")

    return 0 if not missing else 1


if __name__ == "__main__":
    seeds = [int(x) for x in sys.argv[1:]] or [7, 13, 99]
    sys.exit(main(seeds))
