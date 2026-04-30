# CLI-Referenz

Alle Kommandos sind über `sgsim …` (nach `pip install -e .`) oder
`python3.12 -m sgsim.cli …` aufrufbar. Implementiert in `src/sgsim/cli.py`.

## Persistenz und State-Datei

`sgsim` ist ein **stateful CLI-Tool**. Jeder Befehl:
1. Lädt den Grid-Zustand aus `.sgsim_state.json` im aktuellen Verzeichnis
2. Mutiert ihn (Sollwerte, Tick, Curtailment, …)
3. Schreibt ihn zurück

Damit kann **jeder externe Controller** (Skript, Mensch oder LLM) das Grid
zwischen den Ticks steuern, ohne dass der Tool-Code irgendetwas davon weiß.

## Output-Konvention

- **JSON**: alle normalen Befehle geben strukturiertes JSON aus (gut für
  `jq`, andere Tools, oder LLM-Parser).
- **Markdown** (UTF-8): nur `sgsim brief`, weil das ein lesbarer Brief ist.

## Befehle

### Grid-Lebenszyklus

#### `sgsim init [--scenario X.yaml] [--seed N]`
Lädt ein Szenario, baut ein neues `Grid`, schreibt `.sgsim_state.json`.
Default-Szenario: `stadt_mittel`. `--seed` überschreibt den im YAML.

```bash
sgsim init                        # Default-Szenario, Default-Seed
sgsim init --seed 42
sgsim init --scenario meins.yaml
```

#### `sgsim state [--full | --summary]`
Aktuellen Grid-Zustand ausgeben. Default ist eine kompakte Zusammenfassung
mit `last_tick`-Snapshot. `--full` gibt die ganze History aus (groß).

#### `sgsim tick`
Einen Zeitschritt (15 min) vorwärts. Output: das `TickRecord` als JSON.

#### `sgsim run --steps N`
N Ticks ohne Eingriff am Stück. Output: aggregierte Metriken nach dem letzten Tick.

### Steuerung — wie ein Controller eingreift

#### `sgsim dispatch <name> <mw>`
Sollwert für einen Erzeuger oder Speicher setzen.

- Erzeuger: positive MW (z. B. Gas-GuD auf 100 MW)
- Speicher: positive MW = entladen, negative MW = laden

```bash
sgsim dispatch h2_gasturbine 100
sgsim dispatch -- batterie_quartier -50    # negativ → laden, '--' wegen Click
```

`--` ist nötig, damit Click das negative Vorzeichen nicht als Option liest.

#### `sgsim set-curtailment <pv_oder_wind> <0..1>`
PV oder Wind abregeln. `0` = volle Einspeisung, `1` = komplett abgeregelt.

```bash
sgsim set-curtailment pv_aufdach 0.3
```

### Auswertung

#### `sgsim metrics`
Aggregierte Messgrößen seit `init` ausgeben (CO₂, Brownouts, Surplus,
Renewable-Share, Frequenz-Statistik).

#### `sgsim export --out X.csv`
Vollständiges Tick-Protokoll als CSV. Spalten:
- Zeit/Wetter: `step, sim_time_h, hour_of_day, irradiance, wind, temperature`
- Bilanz: `p_total_mw, energy_in_mwh, energy_out_mwh, imbalance_mwh, co2_kg, renewable_energy_mwh`
- Pro Komponente: `P_<name>_mw` (Wirkleistung)
- Pro Komponente mit Snapshot: `D_<name>_<feld>` (z. B. SoC, Curtailment)

### Brief für KI-Controller

#### `sgsim brief [--format text | json]`
Den **kanonischen Master-Brief** für eine KI-Steuerung ausgeben. Das ist die
*einzige* Quelle der Wahrheit für KI-Onboarding (auch der `AnthropicAIController`
lädt diesen Text als System-Prompt).

```bash
sgsim brief                # Markdown auf stdout
sgsim brief --format json  # in JSON-Wrapper
```

Spawn-Prompt für Subagents wird damit zum Einzeiler:
> *"Working dir: X, Seed: N. Run `sgsim brief` und folge den Anweisungen."*

### Self-contained Experimente

Diese Subgruppe lädt **keinen** persistierten State, sondern fährt einen
vollständigen Lauf in einem Prozess durch.

#### `sgsim experiment run --controller X --steps N --seed S --out Y.csv`

Self-contained Vergleichslauf mit gewähltem Controller. Schreibt:
- `Y.csv` — vollständige Tick-Zeitreihe
- `Y.metrics.json` — aggregierte Metriken + **Reproducibility-Hash** +
  Wirtschaftlichkeit (Brennstoff/CO₂/VOLL/Netto/LCOE)

```bash
sgsim experiment run --controller naive       --steps 96 --seed 42 --out r1.csv
sgsim experiment run --controller rule_based  --steps 96 --seed 42 --out r2.csv
sgsim experiment run --controller random_ai   --steps 96 --seed 42 --out r3.csv

# Mit API-Key:
export ANTHROPIC_API_KEY=sk-ant-...
sgsim experiment run --controller anthropic_ai --steps 96 --seed 42 --out r4.csv
```

Gültige `--controller`-Werte: `none, naive, rule_based, random_ai, anthropic_ai`.

#### `sgsim experiment compare run1.csv run2.csv …`

Mehrere CSV-Läufe gegenüberstellen. Erste Datei = Baseline; weitere Runs werden
in Prozent-Differenzen angezeigt.

```bash
sgsim experiment compare r1.csv r2.csv r3.csv
```

## Fehlerquellen / häufige Stolpersteine

- **`no_state`**: kein `.sgsim_state.json` gefunden. Erst `sgsim init` aufrufen.
- **`unknown component`**: Komponentenname tippt — siehe `sgsim state`.
- **Click parst negative Zahl als Option**: `sgsim dispatch -- name -50` mit
  doppelten Bindestrichen vor dem Komponentennamen.
- **`UnicodeEncodeError` auf Windows**: betrifft nur `sgsim brief` mit
  manueller Pipe — die CLI nutzt `sys.stdout.buffer` (UTF-8), aber externe
  Tools können stolpern. `sgsim brief --format json` umgeht das.

## Verwandte Doku

- [`controllers.md`](controllers.md) — was die einzelnen Controller machen
- [`experiments.md`](experiments.md) — vollständige Statistik-Pipeline
- [`components.md`](components.md) — welche Komponentennamen es gibt
