"""Erzeugt Standard-Plots fuer einen sgsim-Lauf.

Liest eine Tick-CSV (z. B. von `sgsim experiment run --out X.csv`) und
schreibt PNG-Diagramme:
  - Lastganglinie und Erzeugungsmix gestapelt
  - Speicher-SoC-Verlaeufe (Batterie, Pumpspeicher, H2-Speicher)
  - Imbalance / CO2 ueber Zeit
  - Tagessumme als Bilanz-Sankey (vereinfacht, als Bar-Plot)

Usage:
    python scripts/plot_run.py results/rule_based.csv [--out plots/rule_based]
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--out", type=Path, default=None,
                        help="Ausgabeverzeichnis (Default: <csv-dir>/plots/<csv-stem>/)")
    args = parser.parse_args()

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        raise SystemExit("matplotlib nicht installiert. 'pip install matplotlib'")

    out_dir = args.out or args.csv_path.parent / "plots" / args.csv_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    with args.csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    if not rows:
        raise SystemExit(f"keine Daten in {args.csv_path}")

    t = [float(r["sim_time_h"]) for r in rows]

    # ---- Power components (P_<name>_mw Spalten) ------------------------
    p_cols = [k for k in rows[0].keys() if k.startswith("P_") and k.endswith("_mw")]
    # Heuristik: was ist Erzeugung (>0 ueblicherweise) vs. Last (<0 ueblicherweise)
    series: dict[str, list[float]] = {c: [float(r[c] or 0) for r in rows] for c in p_cols}

    # Erzeugung: positive Komponenten (zeitlicher Mittelwert > 0)
    gen_cols = [c for c, v in series.items() if sum(v) / max(len(v), 1) > 0]
    load_cols = [c for c, v in series.items() if sum(v) / max(len(v), 1) <= 0]

    # ---- Plot 1: Erzeugungsmix gestapelt + Last als Linie ---------------
    fig, ax = plt.subplots(figsize=(11, 5))
    if gen_cols:
        gen_arrays = [series[c] for c in gen_cols]
        labels = [c.removeprefix("P_").removesuffix("_mw") for c in gen_cols]
        ax.stackplot(t, gen_arrays, labels=labels, alpha=0.8)
    if load_cols:
        total_load = [-sum(series[c][i] for c in load_cols) for i in range(len(t))]
        ax.plot(t, total_load, color="black", linewidth=2, label="Gesamtlast (positiv)")
    ax.set_xlabel("Sim-Zeit [h]")
    ax.set_ylabel("Leistung [MW]")
    ax.set_title(f"Erzeugungsmix und Last — {args.csv_path.stem}")
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "01_generation_mix.png", dpi=120)
    plt.close(fig)

    # ---- Plot 2: Speicher-SoC ------------------------------------------
    soc_cols = [k for k in rows[0].keys()
                if k.startswith("D_") and k.endswith("_soc_mwh")]
    if soc_cols:
        fig, ax = plt.subplots(figsize=(11, 4))
        for c in soc_cols:
            try:
                vals = [float(r[c]) if r[c] else None for r in rows]
            except ValueError:
                continue
            label = c.removeprefix("D_").removesuffix("_soc_mwh")
            ax.plot(t, vals, label=label, linewidth=1.5)
        ax.set_xlabel("Sim-Zeit [h]")
        ax.set_ylabel("State of Charge [MWh]")
        ax.set_title(f"Speicher-Fuellstaende — {args.csv_path.stem}")
        ax.legend(loc="best", fontsize=8)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(out_dir / "02_storage_soc.png", dpi=120)
        plt.close(fig)

    # ---- Plot 3: Imbalance + kumuliertes CO2 ---------------------------
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    p_total = [float(r["p_total_mw"]) for r in rows]
    co2 = [float(r["co2_kg"]) for r in rows]
    co2_cum = []
    s = 0.0
    for v in co2:
        s += v
        co2_cum.append(s)

    ax1.plot(t, p_total, color="#c0392b", linewidth=1.2)
    ax1.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax1.fill_between(t, p_total, 0, where=[v < 0 for v in p_total],
                     alpha=0.3, color="#c0392b", label="Defizit (Brownout)")
    ax1.fill_between(t, p_total, 0, where=[v > 0 for v in p_total],
                     alpha=0.3, color="#27ae60", label="Surplus")
    ax1.set_ylabel("P_total [MW]")
    ax1.set_title("Bilanz und CO2 ueber Zeit")
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)

    ax2.plot(t, co2_cum, color="#34495e", linewidth=1.5)
    ax2.set_ylabel("kumuliertes CO2 [kg]")
    ax2.set_xlabel("Sim-Zeit [h]")
    ax2.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "03_imbalance_co2.png", dpi=120)
    plt.close(fig)

    # ---- Plot 4: Tagesbilanz als Bar-Plot ------------------------------
    fig, ax = plt.subplots(figsize=(8, 5))
    totals: dict[str, float] = {}
    dt_h = float(rows[1]["sim_time_h"]) - float(rows[0]["sim_time_h"]) if len(rows) > 1 else 0.25
    for c in gen_cols + load_cols:
        label = c.removeprefix("P_").removesuffix("_mw")
        totals[label] = sum(series[c]) * dt_h
    sorted_keys = sorted(totals, key=totals.get)
    values = [totals[k] for k in sorted_keys]
    colors = ["#c0392b" if v < 0 else "#27ae60" for v in values]
    ax.barh(sorted_keys, values, color=colors)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Energie [MWh]   (negativ = Last/Speicher-Laden)")
    ax.set_title(f"Tagesbilanz nach Komponente — {args.csv_path.stem}")
    ax.grid(True, alpha=0.3, axis="x")
    fig.tight_layout()
    fig.savefig(out_dir / "04_daily_balance.png", dpi=120)
    plt.close(fig)

    print(f"Plots geschrieben nach: {out_dir}")


if __name__ == "__main__":
    main()
