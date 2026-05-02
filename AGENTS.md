# AGENTS.md — Onboarding für Codex-Sessions

Dieses Repo ist `sgsim`: ein **CLI-gesteuerter Smart-Grid-Simulator**, der als
**physikalisches Experiment für eine Physik-Seminararbeit (Abitur)** dient.
Das Modell ist **100 % erneuerbar** und untersucht, ob eine LLM-Steuerung die
Versorgungssicherheit gegenüber regelbasierten Heuristiken verbessern kann.

## Worauf du dich verlassen kannst

- **Python-Paket**: `src/sgsim/` (editable installiert mit `pip install -e .`).
  Aufruf entweder `sgsim …` oder `python3.12 -m sgsim.cli …`.
- **Pakets-Daten**: Szenarien in `src/sgsim/scenarios/*.yaml`, KI-Brief in
  `src/sgsim/ai/master_prompt.md` (auch über `sgsim brief` lesbar).
- **Persistenz** zwischen CLI-Aufrufen: `.sgsim_state.json` im aktuellen Verzeichnis.
- **Tests**: `pytest` aus dem Repo-Root, aktuell **92 Tests grün**.
- **Plattform**: Windows + Bash. Python 3.12 wird über `python3.12` aufgerufen.
- **Encoding**: stdout-Output für Markdown muss über `sys.stdout.buffer` (UTF-8)
  geschrieben werden, sonst cp1252-Fehler bei Sonderzeichen wie CO₂.

## Wo finde ich was?

| Frage | Antwort |
|---|---|
| Was kann die Software? | [`docs/INDEX.md`](docs/INDEX.md) → Übersicht aller Doku |
| Wie ist sie aufgebaut? | [`docs/architecture.md`](docs/architecture.md) |
| Welche Komponenten? | [`docs/components.md`](docs/components.md) |
| CLI-Befehle? | [`docs/cli.md`](docs/cli.md) |
| Steuerungs­strategien? | [`docs/controllers.md`](docs/controllers.md) |
| Wie Vergleichsläufe? | [`docs/experiments.md`](docs/experiments.md) |
| Forschungsfrage? | [`docs/research-question.md`](docs/research-question.md) |
| Modell-Annahmen? | [`docs/methodology.md`](docs/methodology.md) |
| Eigene Komponenten? | [`docs/dev/extending.md`](docs/dev/extending.md) |
| Erster Live-Lauf | [`docs/claude_live_run_seed42.md`](docs/claude_live_run_seed42.md) |

## Kernkonventionen

- **Vorzeichen Wirkleistung [MW]**: Erzeuger > 0, Lasten < 0, Speicher > 0
  beim Entladen. Siehe `src/sgsim/components/base.py`.
- **CLI-Persistenz**: Jeder Befehl lädt State, mutiert ihn, schreibt ihn zurück.
- **Determinismus**: über `--seed`. Reproducibility-Hash in jedem `metrics.json`.
- **Zeitschritt** Default 15 min (96 pro Tag, 24 h Standard-Lauf).
- **Auf Deutsch** mit dem Nutzer kommunizieren (er schreibt eine deutsche
  Seminararbeit).

## Tipps für Codex

- **KI-Steuerung in einer Schleife**: nutze `sgsim brief` als Onboarding für
  Subagents — das ist der kanonische Master-Prompt, kein Copy-Paste nötig.
- **Bei Änderungen am Modell**: `docs/methodology.md` aktualisieren — das ist
  die Verteidigungslinie der Seminararbeit.
- **Tests bei jeder Änderung**: `python3.12 -m pytest`. Property-Tests
  (parametrisiert über Seeds) decken Bilanzfehler zuverlässig auf.
- **Vor dem Commit**: `.sgsim_state.json` und `results/` löschen, sind
  transient.
- **Ausgaben sind JSON** — andere Tools können sie parsen. Markdown-Output nur
  bei `sgsim brief` über `sys.stdout.buffer`.

## Kritische Stellen, an denen ich nicht ohne guten Grund eingreifen würde

- `Component.step()`-Signatur: jede Komponente liefert genau eine Wirkleistung
  pro Tick. Erweiterungen über `snapshot()`-Hook für Logging.
- Engine-Tick-Reihenfolge: erst Komponenten, dann Bilanz, dann Frequenz,
  dann TickRecord. Beim Refactor leicht zu zerstören.
- `apply_action()`-Validierung: Aktionen unbekannter Komponenten oder
  ungültige Werte erzeugen Warnungen, **brechen nicht ab** — sonst kann ein
  schlechter LLM-Output das Experiment killen.
- `RENEWABLE_TYPES` in `engine.py`: wenn neue erneuerbare Komponente, bitte
  hier eintragen (sonst falsche Renewable-Share).

## Schnellstart-Block für eine neue Session

```bash
cd C:/Users/pnino/Desktop/smartgridsim
python3.12 -m pytest                              # 92 Tests
python3.12 -m sgsim.cli init                      # Default-Szenario
python3.12 -m sgsim.cli experiment run --controller rule_based --steps 96 --out r.csv
python3.12 -m sgsim.cli brief                     # Master-Prompt für KI
```
