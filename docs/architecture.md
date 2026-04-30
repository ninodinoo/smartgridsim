# Architektur

`sgsim` ist in **sechs klar getrennte Schichten** aufgebaut. Jede Schicht hat
genau eine Aufgabe; der Code an einer Stelle "weiß" nichts von Aufgaben anderer
Schichten. Das macht die Software erweiterbar und wissenschaftlich verteidigbar.

## Datenfluss eines Ticks (15 Minuten Simulation)

```
                ┌─────────────────────┐
                │   SyntheticWeather  │  weather.py — deterministisch
                │   (Seed → Strahlung,│  (oder CsvWeather)
                │    Wind, Temperatur)│
                └──────────┬──────────┘
                           │ TickContext
                           ▼
   ┌────────────────────────────────────────┐
   │              Grid.tick()               │  engine.py
   │   1. Für jede Komponente:              │
   │       P_i = component.step(dt, ctx)    │
   │   2. Bilanz: P_total = Σ P_i           │
   │   3. Energie/CO₂/Renewable buchen      │
   │   4. Frequenz: f = 50 + droop · P_tot  │
   │   5. TickRecord ans History anhängen   │
   │   6. sim_time_h += dt_h                │
   └─────────────────────┬──────────────────┘
                         │
                         ▼
                   .sgsim_state.json     (JSON-Persistenz)
```

## Die sechs Schichten

### Schicht 1 — Komponenten (`src/sgsim/components/`)

Physik der Netzteilnehmer. Jede Komponente erbt von `Component` (`base.py`)
und liefert pro Tick eine Wirkleistung [MW]:

```python
def step(self, dt_h, ctx) -> float: ...
```

Vorzeichen-Konvention (Modul-Docstring):
- Erzeuger: P > 0
- Lasten: P < 0
- Speicher: P > 0 (entladen), P < 0 (laden)

Submodule:
- `base.py` — `Component` ABC + `TickContext`
- `loads.py` — BDEW-ähnliche Lasten (H0, G0, L0)
- `renewables.py` — PV, Wind, Laufwasser
- `dispatchable.py` — regelbare thermische/Bio-Erzeuger
- `storage.py` — Batterie, Pumpspeicher, H₂-Speicher
- `sector_coupling.py` — Wärmepumpe, V2G-Flotte, Elektrolyseur

Komponenten-Details: [`components.md`](components.md).

### Schicht 2 — Wetter & Daten (`src/sgsim/weather.py`, `data_loaders.py`)

Liefert für jeden Zeitpunkt: Globalstrahlung, Windgeschwindigkeit, Temperatur.

- `SyntheticWeather` — deterministischer Sinus-Tagesgang + Rauschen via Seed.
- `CsvWeather` — liest echte Daten (DWD/PVGIS) aus CSV; fällt auf
  `SyntheticWeather` zurück, wenn kein Pfad gegeben ist.

### Schicht 3 — Engine (`src/sgsim/engine.py`)

Die Simulationsmaschine: hält `Grid` mit allen Komponenten, führt Ticks aus,
bucht Energie/CO₂/Renewable und Frequenz, schreibt JSON-State.

`Grid.tick()` ist der Kern. `Grid.run(N)` macht N Ticks am Stück.
Persistenz: `Grid.save()` / `Grid.load()` über JSON.

Wichtige Eigenschaft: **die Engine kennt keine Strategie**. Sie führt nur
Physik aus. Wer Setpoints setzt, ist Aufgabe der Schichten 4–6.

### Schicht 4 — Controller (`src/sgsim/controllers/`)

Strategien, die zwischen den Ticks Setpoints/Curtailment auf Komponenten
schreiben. Basis-ABC mit zwei Methoden:

```python
def initialize(self, grid): ...      # einmal vor Tick 0
def step(self, grid, next_ctx): ...  # vor jedem Tick
```

Konkrete Strategien:
- `naive.py` — statische Sollwerte, bleibt unverändert.
- `rule_based.py` — Merit-Order + Speicher-Heuristik + Curtailment.

Details: [`controllers.md`](controllers.md).

### Schicht 5 — KI-Schnittstelle (`src/sgsim/ai/`)

Spezialisierung von Schicht 4 für LLM-Controller:

- `state.py` — `grid_snapshot(grid, next_ctx) → dict`: kompakter JSON-Zustand
  für einen externen Decider.
- `action.py` — `apply_action(grid, action_dict) → warnings`: Aktion
  validieren und auf Grid anwenden.
- `controllers.py` — `AILoopController` (ABC mit `decide(state) → action`),
  `RandomAIController` (Demo), `AnthropicAIController` (echte API mit
  Prompt-Caching).
- `master_prompt.md` — kanonischer Brief (auch via `sgsim brief` lesbar).

### Schicht 6 — CLI (`src/sgsim/cli.py`) + Experiment-Runner (`experiment.py`)

Click-basierte CLI, jede Operation lädt-mutiert-schreibt `.sgsim_state.json`.
Damit kann ein externer Controller (Mensch oder LLM) den Simulator zwischen
Ticks steuern.

Subgruppe `experiment` für self-contained Vergleichsläufe ohne State-File.
Details: [`cli.md`](cli.md).

## Hilfsmodule

- `frequency.py` — quasi-statische Droop-Approximation der Netzfrequenz
- `forecast.py` — `noisy_forecast()` für Rauschen auf Wettervorhersagen
- `economics.py` — Brennstoff-, CO₂-, VOLL-Kosten und LCOE
- `data_loaders.py` — CSV-Schnittstelle für reale BDEW/DWD-Daten

## Modulkarte

```
src/sgsim/
├── __init__.py         (Version)
├── components/         Schicht 1 — Physik der Netzteilnehmer
│   ├── base.py             ABC + TickContext
│   ├── loads.py            Wohnen / Gewerbe / Industrie
│   ├── renewables.py       PV / Wind / Laufwasser
│   ├── dispatchable.py     Bio / Geothermie / Gas / Kohle / H2-GuD
│   ├── storage.py          Battery / Pumpspeicher / H2-Speicher
│   └── sector_coupling.py  HeatPump / EVFleet / Electrolyzer
├── weather.py          Schicht 2 — Synthetisches Wetter
├── data_loaders.py     Schicht 2 — CSV-Schnittstelle für reale Daten
├── engine.py           Schicht 3 — Grid + Tick + Persistenz + Metriken
├── frequency.py        Hilfsmodul: Frequenz (Droop-Approx.)
├── forecast.py         Hilfsmodul: Forecast-Rauschen
├── economics.py        Hilfsmodul: Wirtschaftlichkeit
├── controllers/        Schicht 4 — Steuerungsstrategien
│   ├── base.py             Controller-ABC
│   ├── naive.py            Statische Sollwerte
│   └── rule_based.py       Merit-Order + Speicher-Heuristik
├── ai/                 Schicht 5 — LLM-Schnittstelle
│   ├── state.py            Grid → JSON-Snapshot
│   ├── action.py           JSON-Action → Grid (mit Validierung)
│   ├── controllers.py      RandomAI / AnthropicAI
│   └── master_prompt.md    Kanonischer Brief für LLMs
├── experiment.py       Schicht 6 — Self-contained Vergleichsläufe
├── cli.py              Schicht 6 — CLI (Click)
└── scenarios/
    └── stadt_mittel.yaml   Default: Mittelstadt 100 % erneuerbar

scripts/
├── plot_run.py             matplotlib-Plots aus Tick-CSV
├── compare_strategies.py   n-Seed-Vergleich + Welch-t/Cohen's d
└── aggregate_pilot.py      Aggregat von Subagent-Pilotläufen

tests/
├── test_energy_balance.py     Bilanzerhaltung, Round-Trip
├── test_components.py         Komponenten-Physik
├── test_controllers.py        Naive vs. RuleBased
├── test_ai_pipeline.py        Snapshot, Apply, JSON-Parser
├── test_cli_smoke.py          End-to-End-CLI
├── test_frequency_and_forecast.py  Frequenz, Rauschen, CSV-Loader
└── test_phase5.py             Hash, Wirtschaftlichkeit, Property-Tests
```

## In einem Satz

`sgsim` ist eine **deterministische, komponenten-orientierte
Smart-Grid-Simulation mit pausierbarem Zustand**, deren CLI-Schnittstelle
die saubere Trennung von Physik (Engine) und Steuerung (Controller / AI)
erzwingt.
