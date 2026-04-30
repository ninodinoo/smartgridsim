# Steuerungsstrategien

Vier eingebaute Strategien plus die Möglichkeit, **Claude Code (du) selbst**
über die CLI zu steuern. Implementiert in `src/sgsim/controllers/` und
`src/sgsim/ai/`.

## Schnittstelle

Alle Controller erben von der ABC `Controller` (`controllers/base.py`):

```python
class Controller(ABC):
    def initialize(self, grid): ...      # einmal vor Tick 0
    @abstractmethod
    def step(self, grid, next_ctx): ...  # vor jedem Tick
```

`step()` mutiert das Grid (setzt `setpoint_mw` und `curtailment` auf
Komponenten), gibt nichts zurück. Die Engine ruft danach `tick()`.

## Eingebaute Strategien

### `naive` — bewusst dumme Baseline

Setzt einmalig konstante Sollwerte, ändert danach nichts mehr.

Für das 100 %-erneuerbare Default-Szenario:
- Biomasse 100 % (cheap renewable, immer voll)
- Geothermie 100 %
- H₂-Gasturbine 50 % (mittlere Festlast als Backup)
- HeatPump fix bei 8 MW
- Speicher und EV-Flotte und Electrolyzer passiv

Implementierung: `controllers/naive.py`.

**Wozu?** Der Vergleichspunkt für jede smarte Strategie. Naive überproduziert
bei Mittagswind, kann Lastspitzen nicht abfangen, nutzt keine Speicher.

### `rule_based` — Merit-Order + Speicher-Heuristik

Pro Tick:
1. **Forecast** der Last und nicht-dispatchierbaren Erneuerbaren für den
   nächsten Tick (mit perfect foresight — siehe Caveats unten).
2. Biomasse + Geothermie immer voll.
3. Wärmepumpen folgen ihrem Bedarf (Setpoint = Baseline).
4. Residuallast = Last + WP − Erneuerbar − Bio − Geothermie.
5. **Defizit:** Reihenfolge nach Round-Trip-Wirkungsgrad
   - Batterie entladen (η_rt 0.90)
   - Pumpspeicher entladen (η_rt 0.80)
   - V2G: E-Auto-Flotte einspeisen (max 30 % der Peak-MW als Reserve)
   - H₂-Gasturbine hochfahren
   - H₂-Speicher direkt entladen (η_rt 0.36, letztes Mittel)
6. **Überschuss:**
   - Batterie laden
   - Pumpspeicher laden
   - EV-Flotte laden (70 % Peak-MW, Rest für Mobilität)
   - Elektrolyseur betreiben (Power-to-Gas)
   - H₂-Speicher laden (saisonale Reserve aufbauen)
   - PV/Wind abregeln

Implementierung: `controllers/rule_based.py`.

**Caveats:**
- "Perfect-foresight"-Forecast (sieht den nächsten Tick exakt). Kann mit
  `forecast.noisy_forecast()` verrauscht werden, wenn fairer Vergleich gewollt.
- Heuristik regelt eindimensional (residual MW), kennt keine Zeit-Vorausschau
  über mehrere Ticks. → Hier setzt der KI-Vorteil an.

## KI-Strategien (Schicht 5)

Alle KI-Controller erben von `AILoopController` (in `ai/controllers.py`),
das die Tick-Mechanik kapselt:

```python
def step(self, grid, next_ctx):
    snap = grid_snapshot(grid, next_ctx)         # Grid → JSON
    action = self.decide(snap)                    # JSON → JSON (LLM-Call)
    apply_action(grid, action)                    # JSON → Grid
```

Subklassen müssen nur `decide(state) → action` implementieren.

### `random_ai` — zufällige Setpoints (Demo)

Setzt für jede Komponente zufällige Werte im zulässigen Bereich. Ist als
Schnittstellen-Test gedacht, nicht als ernsthafte Strategie.

**Wozu?** Demonstriert, dass *blinde* Steuerung dramatisch schlechter ist als
selbst die naive Strategie. Wertvolle dritte Vergleichsdimension für die Arbeit.

### `anthropic_ai` — echte LLM-Steuerung

Nutzt die Anthropic-API mit **Prompt-Caching** für den System-Prompt
(Master-Brief aus `src/sgsim/ai/master_prompt.md`). Der Brief enthält
Komponenten-Tabellen, Strategie-Hinweise, Antwort-Format. Pro Tick wird nur
der variable JSON-Snapshot neu geschickt → Token-Kosten gering.

Voraussetzungen:
```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...    # bash/zsh
$env:ANTHROPIC_API_KEY = "sk-ant-..."  # PowerShell
```

Modell-Default: `claude-haiku-4-5` (kosteneffizient für 96 Ticks/Lauf).

## Live-Steuerung über die CLI (du oder Claude in einer Konversation)

**Keine eigene Strategie-Klasse.** Stattdessen wird die CLI direkt verwendet:

```bash
sgsim init
while not_done:
    sgsim state                                  # Zustand lesen
    sgsim dispatch h2_gasturbine 120             # Sollwerte setzen
    sgsim dispatch -- pumpspeicher_alpental -50
    sgsim tick                                    # einen Schritt vor
sgsim export --out claude.csv
```

Diese Form ist die ehrlichste "LLM-im-Loop": Claude liest pro Tick den Zustand,
denkt, entscheidet. Reproduzierbar nur über Konversations-Logging, nicht
deterministisch zwischen Sessions.

Der erste so dokumentierte Lauf liegt in
[`claude_live_run_seed42.md`](claude_live_run_seed42.md) (für das alte
fossile Modell — dient nur noch historisch).

## Vergleich der Strategien

| Strategie | Code-Größe | Vorausschau | LLM-Kosten | Reproduzierbar |
|---|---|---|---|---|
| `naive` | ~50 LoC | nein | 0 | exakt |
| `rule_based` | ~200 LoC | 1 Tick (perfect) | 0 | exakt |
| `random_ai` | ~50 LoC | nein | 0 | exakt (mit Seed) |
| `anthropic_ai` | ~150 LoC | impliziert via LLM | EUR pro Lauf | quasi-deterministisch |
| Live (du) | – | impliziert | – | nur per Log |

## Strategie-Wahl je nach Forschungsfrage

- **"Kann KI besser als regelbasiert?"** → `rule_based` vs. `anthropic_ai`
  über mehrere Seeds, mit Welch-t/Cohen's d.
- **"Wie schlecht ist Nicht-Steuerung?"** → `naive` als Untergrenze.
- **"Ist KI besser als zufällig?"** → `random_ai` als Sanity-Check.
- **"Pilot-Demo, dass es geht"** → manuelle Live-Steuerung in einer Session.

Statistik-Pipeline: [`experiments.md`](experiments.md).
