# Vergleichsläufe und Statistik

Dieses Dokument beschreibt, wie man einen wissenschaftlich belastbaren
Strategie-Vergleich durchführt — von einem einzelnen Lauf bis zu einer
n-Seed-Statistik mit Welch-t-Test und Cohen's d.

## Einzelnen Lauf machen

```bash
sgsim experiment run --controller rule_based \
                     --steps 96 --seed 42 \
                     --out results/rb.csv
```

Output:
- **`results/rb.csv`** — Tick-Zeitreihe (96 Zeilen) mit allen Komponenten-
  Wirkleistungen, Wetter, Bilanz, CO₂, Frequenz.
- **`results/rb.metrics.json`** — aggregierte Metriken + Reproducibility-Hash
  + Wirtschaftlichkeit.

## Mehrere Strategien vergleichen (gleicher Seed)

```bash
sgsim experiment run --controller naive       --seed 42 --steps 96 --out r1.csv
sgsim experiment run --controller rule_based  --seed 42 --steps 96 --out r2.csv
sgsim experiment compare r1.csv r2.csv
```

Der `compare`-Befehl liest die Sidecar-`.metrics.json`, ermittelt prozentuale
Differenzen aller relevanten Metriken zur Baseline (erste Datei).

## Statistik über viele Seeds (für die Seminararbeit)

Das Skript `scripts/compare_strategies.py` fährt automatisch
`n_seeds × n_controllers` Läufe und macht Welch-t-Test plus Cohen's d.

```bash
python3.12 scripts/compare_strategies.py \
    --seeds 1-30 \
    --controllers naive,rule_based \
    --steps 96
```

Output (in `results/comparison/<timestamp>/`):
- **`per_run.csv`** — eine Zeile pro `(controller, seed)`-Kombination
- **`summary.txt`** — Tabelle mit Mittelwert ± Standardabweichung pro
  Strategie, Welch-t-Werten und Cohen's d für die Hauptmetriken
  (CO₂, Brownouts, Surplus, Unserved Energy)

### Beispiel-Ausgabe (n=5 zur Demo)

```
Metrik                                     naive          rule_based
co2_kg                            32546.25 +-   0.00  26955.38 +-  64.96
brownout_steps                       36.40 +-   1.67     69.00 +-   3.16
surplus_energy_mwh                  688.75 +-  17.74     85.06 +-  15.37

Welch-t und Cohen's d (rule_based vs. naive)
  co2_kg                       t = -192.45 ***  d = -121.72
  brownout_steps               t =  +20.38 ***  d =  +12.89
  surplus_energy_mwh           t =  -57.51 ***  d =  -36.38
```

Signifikanzlevel:
- `*` p < 0.05 (|t| > 1.96)
- `**` p < 0.01 (|t| > 2.5)
- `***` p < 0.001 (|t| > 3.5)

Bei n ≥ 30 Seeds und derart hohen t/d-Werten ist die Aussage **hoch
signifikant** — das ist genau das, was die Seminararbeit braucht.

## Plots erzeugen

`scripts/plot_run.py` erzeugt vier Standard-Diagramme aus einer Tick-CSV:

```bash
python3.12 scripts/plot_run.py results/rb.csv
```

Output (in `results/plots/rb/`):
- **`01_generation_mix.png`** — Erzeugungsmix gestapelt + Last als Linie
- **`02_storage_soc.png`** — SoC-Verlauf aller Speicher
- **`03_imbalance_co2.png`** — Bilanz (Surplus grün, Defizit rot) und
  kumuliertes CO₂
- **`04_daily_balance.png`** — Tagessummen pro Komponente als Balkendiagramm

Voraussetzung: `pip install matplotlib`.

## Reproducibility-Hash

Jede `metrics.json` enthält einen 16-Zeichen-Hash, der berechnet wird aus:

- sgsim-Version
- Inhalt der Szenario-Datei
- Seed
- Controller-Name
- Anzahl Schritte
- Python-Version

Damit kann in der Arbeit garantiert werden: *"Der Lauf mit Hash `abc123…`
wurde mit exakt dieser Software-Version, Szenario und Seed erzeugt."*

Implementiert in `experiment.reproducibility_hash()`. Test:
`tests/test_phase5.py`.

## Wirtschaftlichkeitsmetriken

Die Sidecar-JSON enthält einen `economics`-Block mit:

| Schlüssel | Bedeutung | Default-Annahme |
|---|---|---|
| `fuel_cost_eur` | Brennstoffkosten (variabel) | je Erzeuger-Klasse, BNetzA 2023 |
| `co2_cost_eur` | EU-ETS-Zertifikate | 85 EUR/t CO₂ |
| `storage_cost_eur` | Speicher-Lebensdauerkosten | 5 EUR/MWh durchgesetzt |
| `voll_cost_eur` | Value of Lost Load (Brownout-Schaden) | 7000 EUR/MWh |
| `total_cost_eur` | Summe aller Kosten | – |
| `market_revenue_eur` | Erlöse Day-Ahead-Mittelpreis | 95 EUR/MWh |
| `net_eur` | `market_revenue − total_cost` | – |
| `lcoe_eur_per_mwh` | Levelized Cost of Energy | – |

Quellen-Hinweis und Anpassungsmöglichkeiten: `src/sgsim/economics.py`,
[`methodology.md`](methodology.md) §11.

## Empfohlener Ablauf für die Seminararbeit

1. **Pilotlauf** mit n=3–5 Seeds, alle Strategien — Plausibilität prüfen,
   Plots ansehen.
2. **Hauptauswertung** mit n=30 Seeds × `naive`, `rule_based`,
   `anthropic_ai` (oder Live-Claude-Subagents).
3. **Drei Plots** je Strategie aus repräsentativem Seed (z. B. Seed 42).
4. **Statistik-Tabelle** aus `summary.txt` direkt in die Arbeit übernehmen.
5. **Reproducibility-Hashes** im Anhang dokumentieren.

## Subagents für mehrere Live-Läufe

Statt über die Anthropic-API kann man **Claude-Code-Subagents** parallel
starten — jeder mit eigenem Working Directory, eigenem Seed:

```
runs/
├── seed_07/   ← Subagent A
├── seed_13/   ← Subagent B
└── seed_99/   ← Subagent C
```

Spawn-Prompt für jeden Subagent (Einzeiler dank `sgsim brief`):
> *"Working dir: `runs/seed_<N>`. Seed: `<N>`. Run `sgsim brief` und
> folge den Anweisungen."*

Aggregation der Ergebnisse: `scripts/aggregate_pilot.py` liest die einzelnen
`result.metrics.json` und macht denselben Vergleich wie
`compare_strategies.py`.
