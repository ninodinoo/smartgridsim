"""Statistischer Strategievergleich ueber mehrere Seeds.

Faehrt fuer eine Liste von Seeds und Controllern jeweils einen 24h-Lauf,
sammelt die Metriken und macht Welch-t-Test + Cohen's d zwischen Strategien.

Usage:
    python scripts/compare_strategies.py --seeds 1-30 --controllers naive,rule_based --steps 96
    python scripts/compare_strategies.py --seeds 1-10 --controllers rule_based,random_ai

Output:
    results/comparison/<timestamp>/
        per_run.csv            — eine Zeile pro (seed, controller)
        summary.txt            — Tabelle Mittelwert ± Stdabw. + Tests
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from pathlib import Path


def parse_seed_range(spec: str) -> list[int]:
    """'1-30' oder '1,7,13' oder '5' → Liste von ints."""
    seeds: list[int] = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-", 1)
            seeds.extend(range(int(a), int(b) + 1))
        elif part:
            seeds.append(int(part))
    return seeds


def welch_t(x1: list[float], x2: list[float]) -> tuple[float, float]:
    """Welch-t und Cohen's d (pooled)."""
    if len(x1) < 2 or len(x2) < 2:
        return float("nan"), float("nan")
    m1, m2 = statistics.mean(x1), statistics.mean(x2)
    s1, s2 = statistics.stdev(x1), statistics.stdev(x2)
    n1, n2 = len(x1), len(x2)
    se = (s1 ** 2 / n1 + s2 ** 2 / n2) ** 0.5
    t = (m1 - m2) / se if se > 0 else float("nan")
    sp = (((n1 - 1) * s1 ** 2 + (n2 - 1) * s2 ** 2) / (n1 + n2 - 2)) ** 0.5
    d = (m1 - m2) / sp if sp > 0 else float("nan")
    return t, d


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="1-30",
                        help="Seed-Liste, z. B. '1-30' oder '1,7,13'")
    parser.add_argument("--controllers", default="naive,rule_based",
                        help="Komma-Liste der Controller-Namen")
    parser.add_argument("--steps", type=int, default=96)
    parser.add_argument("--scenario", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    if args.scenario is None:
        args.scenario = Path(__file__).parent.parent / "src" / "sgsim" / "scenarios" / "stadt_mittel.yaml"

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = args.out or Path("results") / "comparison" / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    seeds = parse_seed_range(args.seeds)
    controllers = [c.strip() for c in args.controllers.split(",")]

    # Lazy import: spaerlich, weil sgsim viele Module zieht
    from sgsim.experiment import run_experiment

    metric_keys = (
        "co2_kg", "renewable_share_of_demand", "energy_consumed_mwh",
        "energy_generated_mwh", "surplus_energy_mwh", "unserved_energy_mwh",
        "brownout_steps", "peak_deficit_mw", "peak_surplus_mw",
    )

    per_run: list[dict] = []
    by_ctrl: dict[str, dict[str, list[float]]] = {c: {k: [] for k in metric_keys}
                                                   for c in controllers}

    print(f"Laufe {len(seeds) * len(controllers)} Simulationen "
          f"({len(seeds)} Seeds x {len(controllers)} Strategien)...")
    for ctrl in controllers:
        for seed in seeds:
            grid, _ = run_experiment(args.scenario, ctrl, args.steps, seed=seed)
            m = grid.metrics()
            row = {"controller": ctrl, "seed": seed, **{k: m.get(k) for k in metric_keys}}
            per_run.append(row)
            for k in metric_keys:
                by_ctrl[ctrl][k].append(float(m.get(k, 0) or 0))
            print(f"  [{ctrl} seed={seed}] CO2={m.get('co2_kg', 0):.0f} "
                  f"brownouts={m.get('brownout_steps', 0)}")

    # Per-run-CSV
    per_run_path = out_dir / "per_run.csv"
    with per_run_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["controller", "seed", *metric_keys])
        w.writeheader()
        w.writerows(per_run)

    # Aggregat-Tabelle
    summary_path = out_dir / "summary.txt"
    lines: list[str] = []
    lines.append(f"Strategievergleich  Seeds={seeds}  Steps={args.steps}")
    lines.append("=" * 90)
    lines.append("")
    header = f"{'Metrik':<32}" + "".join(f"{c:>20}" for c in controllers)
    lines.append(header)
    lines.append("-" * len(header))
    for k in metric_keys:
        cells = []
        for c in controllers:
            v = by_ctrl[c][k]
            if not v:
                cells.append("n/a")
            elif len(v) > 1:
                cells.append(f"{statistics.mean(v):8.2f} +- {statistics.stdev(v):6.2f}")
            else:
                cells.append(f"{v[0]:8.2f}")
        lines.append(f"{k:<32}" + "".join(f"{c:>20}" for c in cells))

    # Welch-t / Cohen's d
    if len(controllers) >= 2 and len(seeds) >= 2:
        lines.append("")
        lines.append(f"Welch-t und Cohen's d (Vergleich {controllers[1]} vs. {controllers[0]})")
        lines.append("-" * 60)
        for k in ("co2_kg", "brownout_steps", "surplus_energy_mwh",
                  "unserved_energy_mwh"):
            t, d = welch_t(by_ctrl[controllers[1]][k], by_ctrl[controllers[0]][k])
            sig = "***" if abs(t) > 3.5 else ("**" if abs(t) > 2.5 else (
                "*" if abs(t) > 1.96 else ""))
            lines.append(f"  {k:<28} t = {t:+7.2f} {sig:<3}  d = {d:+5.2f}")

    text = "\n".join(lines)
    summary_path.write_text(text + "\n", encoding="utf-8")
    print()
    print(text)
    print(f"\nGeschrieben:\n  {per_run_path}\n  {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
