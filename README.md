<div align="center">

# ⚡ sgsim

### CLI-gesteuerter Smart-Grid-Simulator (100 % erneuerbar)

**Kann eine KI-Steuerung ein 100 %-erneuerbares Stromsystem
zuverlässiger versorgen als regelbasierte Heuristiken?**

Ein deterministisches physikalisches Experiment für eine
Physik-Seminararbeit (Abitur).

[![Tests](https://img.shields.io/badge/tests-92%20passed-brightgreen)](#tests)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-private-lightgrey)](#)
[![100%25 Renewable](https://img.shields.io/badge/grid-100%25%20renewable-green)](docs/methodology.md)

</div>

---

## 🌱 Worum geht's

Klassische Smart-Grid-Steuerungen sind regelbasierte Heuristiken (Merit-Order,
Speicher-Ampelregeln). Ihre Leistung ist gut dokumentiert für **fossile Mixe**.
Aber in einem **100 %-erneuerbaren Stromsystem** mit volatiler PV/Wind-Einspeisung
wird **Versorgungssicherheit** zur eigentlichen Herausforderung — nicht mehr
CO₂-Reduktion.

`sgsim` ist die deterministische Simulation, mit der genau diese Frage
**physikalisch sauber gemessen** werden kann.

```
                ┌─────────────────────┐
                │   SyntheticWeather  │  ← deterministisch via Seed
                │   (Strahlung, Wind, │
                │    Temperatur)      │
                └──────────┬──────────┘
                           │
                           ▼
   ┌────────────────────────────────────────┐
   │           Grid.tick() (15 min)         │
   │   1. P_i = component.step(dt, ctx)     │ ← Physik
   │   2. Bilanz: P_total = Σ P_i           │
   │   3. CO₂, Renewable buchen             │
   │   4. Frequenz: f = 50 + droop · ΔP     │
   │   5. TickRecord ans History anhängen   │
   └─────────────────────┬──────────────────┘
                         │
                         ▼
                   .sgsim_state.json
```

## ⚡ Quickstart

```bash
git clone https://github.com/ninodinoo/smartgridsim
cd smartgridsim
pip install -e .[dev]

# 24-h-Lauf mit regelbasierter Steuerung
sgsim experiment run --controller rule_based --steps 96 --seed 42 --out rb.csv

# Vergleich gegen statische Steuerung
sgsim experiment run --controller naive --steps 96 --seed 42 --out naive.csv
sgsim experiment compare naive.csv rb.csv

# KI-Brief lesen (für eine LLM-Steuerung)
sgsim brief
```

## 🧠 Was ist neu?

Die spannendste Eigenschaft des Tools: **die CLI hält den Simulationszustand
zwischen Aufrufen.** Damit kann *jeder* Controller das Grid steuern — ein
Skript, ein LLM über die Anthropic-API, oder Claude Code direkt in einer
Konversation, **ohne dass die Engine das wissen muss**.

```bash
sgsim init                       # Grid initialisieren
sgsim state                      # Zustand lesen (JSON)
sgsim dispatch h2_gasturbine 100 # Sollwert setzen
sgsim tick                       # einen Schritt vorwärts
sgsim metrics                    # aggregierte Messwerte
```

## 🏗️ Modell-Komponenten

100 % erneuerbares Setup einer Mittelstadt (~150 000 EW):

<table>
<tr>
<td>

**Erzeugung**
- 200 MWp PV (Aufdach)
- 48 MW Onshore-Wind
- 50 MW Offshore-Anteil
- 12 MW Laufwasserkraft
- 25 MW Biomasse
- 8 MW Geothermie
- 200 MW H₂-Gasturbine (Backup)

</td>
<td>

**Speicher (3 Zeitskalen)**
- Batterie: 200 MWh, η_rt 0.90
- Pumpspeicher: 980 MWh, η_rt 0.80
- H₂-Langzeitspeicher: 5 GWh, η_rt 0.36

**Sektorkopplung**
- Wärmepumpen mit thermischem Puffer
- V2G-Flotte (5000 E-Autos)
- Elektrolyseur (Power-to-Gas)

</td>
</tr>
</table>

Physik-Formeln, Parameter und Quellen: [`docs/components.md`](docs/components.md).

## 🎯 Forschungsfrage

> **H1:** Eine LLM-basierte Steuerung senkt die Anzahl der Brownouts
> (Versorgungsausfälle) gegenüber einer regelbasierten Steuerung um
> mindestens 30 %, ohne CO₂ oder Energieverschwendung signifikant
> zu erhöhen.

Pre-Registration, Variablen, Experimentaldesign:
[`docs/research-question.md`](docs/research-question.md).

## 📊 Erste Vergleichszahlen (24 h, Seed 42, Naive vs. RuleBased)

| Metrik | Naive | RuleBased | Δ |
|---|---|---|---|
| CO₂ [t] | 33 kg | 28 kg | **−15 %** |
| Surplus [MWh] | 678 | 103 | **−85 %** |
| Brownout-Ticks | 38 | 63 | +66 % |
| Renewable Share | 56 % | 57 % | +1 % |

> Die regelbasierte Strategie reduziert Verschwendung dramatisch, **erleidet
> aber mehr Brownouts** — genau hier setzt die KI-Steuerung an.

Statistik mit n=30 Seeds + Welch-t / Cohen's d:
[`docs/experiments.md`](docs/experiments.md).

## 📚 Vollständige Dokumentation

| Datei | Inhalt |
|---|---|
| [`docs/INDEX.md`](docs/INDEX.md) | **Navigation aller Doku-Dateien** |
| [`docs/architecture.md`](docs/architecture.md) | 6-Schichten-Architektur, Datenfluss |
| [`docs/components.md`](docs/components.md) | Komponenten-Katalog mit Physik-Formeln |
| [`docs/cli.md`](docs/cli.md) | Vollständige CLI-Referenz |
| [`docs/controllers.md`](docs/controllers.md) | Steuerungsstrategien |
| [`docs/experiments.md`](docs/experiments.md) | Vergleichsläufe + Statistik + Plots |
| [`docs/research-question.md`](docs/research-question.md) | Forschungsfrage |
| [`docs/methodology.md`](docs/methodology.md) | Modell-Annahmen, Vereinfachungen |
| [`docs/dev/extending.md`](docs/dev/extending.md) | Eigene Komponenten/Controller |

## 🧪 Tests

```bash
pytest
```

92 Tests prüfen physikalische Konsistenz (Energiebilanz für jeden Seed,
Speicher-SoC-Grenzen, Frequenzcap), CLI-End-to-End, Serialisierung,
Heuristik-Eigenschaften.

```
tests/
├── test_energy_balance.py            Bilanzerhaltung, Round-Trip
├── test_components.py                Komponenten-Physik
├── test_controllers.py               Naive vs. RuleBased
├── test_ai_pipeline.py               Snapshot, Apply, JSON-Parser
├── test_cli_smoke.py                 End-to-End-CLI
├── test_frequency_and_forecast.py    Frequenz, Rauschen, CSV-Loader
└── test_phase5.py                    Hash, Wirtschaftlichkeit, Property-Tests
```

## 🛠️ Tech-Stack

- **Python 3.12+** mit Standard-Bibliotheken
- **Click** für die CLI
- **PyYAML** für Szenarien
- **NumPy** für Numerik
- **matplotlib** für Plots
- **anthropic** SDK (optional) für LLM-Steuerung
- **pytest** mit parametrisierten Property-Tests

## 🔬 Entstehung

Dieses Projekt ist im Rahmen einer **Physik-Seminararbeit für das Abitur**
entstanden. Die Implementierung ist eine Kollaboration zwischen mir
und Claude (Anthropic): die Architektur, die wissenschaftlichen Ent-
scheidungen und das Gesamtkonzept liegen bei mir; Claude hat den Code
unter meiner Anleitung geschrieben.

Der erste Live-Lauf, in dem Claude das Grid tatsächlich Tick für Tick
gesteuert hat, ist dokumentiert in
[`docs/claude_live_run_seed42.md`](docs/claude_live_run_seed42.md).

## 📜 Lizenz

Privat erarbeitete Seminararbeitssoftware. Keine Garantie für die
physikalische Genauigkeit über das hinaus, was
[`docs/methodology.md`](docs/methodology.md) explizit dokumentiert.

---

<div align="center">

**[Doku-Index →](docs/INDEX.md)**  ·  **[Forschungsfrage →](docs/research-question.md)**  ·  **[Architektur →](docs/architecture.md)**

</div>
