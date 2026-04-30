# sgsim — Smart-Grid-Simulator (100 % erneuerbar)

Ein **CLI-gesteuerter Smart-Grid-Simulator** als physikalisches Experiment für
eine **Physik-Seminararbeit (Abitur)**. Untersucht wird die Frage:

> **Kann eine LLM-basierte Steuerung in einem 100 %-erneuerbaren Stromsystem
> die Versorgungssicherheit verbessern, ohne CO₂ steigen zu lassen oder Energie
> zu verschwenden?**

## In drei Sätzen

- Eine **deterministische Simulation** einer mittelgroßen Stadt (~150 000 EW),
  ausschließlich mit erneuerbaren Quellen + Wasserstoff-Backup.
- Die **CLI hält den Zustand zwischen Aufrufen** — damit kann *jeder* externe
  Controller (regelbasiertes Skript, Anthropic-API, oder du selbst tick-by-tick)
  das Grid steuern, ohne dass die Engine das wissen muss.
- Drei Vergleichs-Strategien sind eingebaut: **`naive`** (statische Sollwerte),
  **`rule_based`** (Merit-Order + Speicher-Heuristik), **`anthropic_ai`** (LLM
  mit Prompt-Caching).

## Quickstart

```bash
pip install -e .[dev]

# 24-h-Lauf mit regelbasierter Steuerung
sgsim experiment run --controller rule_based --steps 96 --seed 42 --out rb.csv

# Vergleich mit naiver Steuerung
sgsim experiment run --controller naive --steps 96 --seed 42 --out naive.csv
sgsim experiment compare naive.csv rb.csv

# Master-Brief für eine LLM-Steuerung ausgeben
sgsim brief
```

## Was die Simulation kann

- **Modell**: 100 % erneuerbares Stromsystem mit allen wichtigen Komponenten
  (PV, Onshore- und Offshore-Wind, Laufwasser, Biomasse, Geothermie,
  H₂-Gasturbine als Backup, Batterie, Pumpspeicher, H₂-Langzeitspeicher,
  Wärmepumpen, V2G-E-Auto-Flotte, Elektrolyseur).
- **Physikalisch fundiert**: $P_{PV} = G \cdot A \cdot \eta$,
  $P_{Wind} = \tfrac{1}{2}\rho A v^3 c_p$, $E_{PSW} = \rho V g h$, Frequenz
  über Droop-Approximation, Wirkungsgrade je Speicher (η_rt 0.36 – 0.90).
- **Vergleich** durch CSV-Export, Statistik-Skripte (Welch-t, Cohen's d
  über mehrere Seeds), Plot-Skripte (matplotlib).
- **Wirtschaftlichkeit** mit Brennstoffkosten, EU-ETS-Zertifikaten, Value of
  Lost Load (VOLL) und LCOE.
- **Reproducibility-Hash** in jedem `metrics.json` für überprüfbare Ergebnisse.
- **Tests**: 92 grün (Bilanzerhaltung, Property-Tests über mehrere Seeds,
  CLI-End-to-End, Komponenten-Physik).

## Dokumentation

| Datei | Inhalt |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | Onboarding für Claude-Code-Sessions |
| [`docs/INDEX.md`](docs/INDEX.md) | **Übersicht aller Doku-Dateien** |
| [`docs/architecture.md`](docs/architecture.md) | 6-Schichten-Architektur, Datenfluss |
| [`docs/components.md`](docs/components.md) | Alle Komponenten mit Physik & Parametern |
| [`docs/cli.md`](docs/cli.md) | Vollständige CLI-Referenz |
| [`docs/controllers.md`](docs/controllers.md) | Steuerungsstrategien |
| [`docs/experiments.md`](docs/experiments.md) | Vergleichsläufe und Statistik |
| [`docs/research-question.md`](docs/research-question.md) | Forschungsfrage der Seminararbeit |
| [`docs/methodology.md`](docs/methodology.md) | Modell-Annahmen, Vereinfachungen, Quellen |
| [`docs/dev/extending.md`](docs/dev/extending.md) | Eigene Komponenten/Controller schreiben |

## Tests

```bash
pytest
```

92 Tests prüfen physikalische Konsistenz (Energiebilanz für jeden Seed,
Speicher-SoC-Grenzen, Frequenzcap), CLI-End-to-End, Serialisierung,
und Heuristik-Eigenschaften.

## Lizenz / Hinweis

Privat erarbeitete Seminararbeitssoftware. Keine Garantie für die
physikalische Genauigkeit über das hinaus, was [`docs/methodology.md`](docs/methodology.md)
explizit dokumentiert.
