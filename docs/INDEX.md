# Dokumentations-Übersicht

Alle MD-Dateien des Projekts an einem Ort. Lies sie in dieser Reihenfolge,
wenn du das Projekt zum ersten Mal kennenlernen willst:

## Einstieg (lesen, wenn neu im Repo)

1. [`../README.md`](../README.md) — Projekt in drei Sätzen, Quickstart, Tests
2. [`../CLAUDE.md`](../CLAUDE.md) — Onboarding für Claude-Code-Sessions
3. [`research-question.md`](research-question.md) — Wissenschaftliche Frage
   und Hypothese der Seminararbeit
4. [`architecture.md`](architecture.md) — Wie ist die Software aufgebaut

## Referenz (nachschlagen, wenn man konkret arbeitet)

5. [`components.md`](components.md) — Komponenten-Katalog mit Physik-Formeln,
   Parametern, Vorzeichen-Konvention
6. [`cli.md`](cli.md) — Vollständige CLI-Referenz, jeder Befehl mit Beispiel
7. [`controllers.md`](controllers.md) — Steuerungsstrategien (Naive,
   RuleBased, RandomAI, AnthropicAI, Live-Steuerung)
8. [`experiments.md`](experiments.md) — Vergleichsläufe, Statistik,
   Plot-Generierung

## Wissenschaftliche Doku

9. [`methodology.md`](methodology.md) — Modell-Annahmen, Vereinfachungen,
   Datenquellen, bekannte Schwächen — **die Verteidigungslinie der
   Seminararbeit**

## Praxis-Berichte

10. [`claude_live_run_seed42.md`](claude_live_run_seed42.md) — Erster echter
    Live-Lauf mit Claude-im-Loop (Seed 42, fossiles Modell — historisch)

## Für Entwickler

11. [`dev/extending.md`](dev/extending.md) — Eigene Komponenten oder
    Controller schreiben

## Brief für KI-Controller (eigenes Format, kein klassischer Doku-Eintrag)

Liegt unter [`../src/sgsim/ai/master_prompt.md`](../src/sgsim/ai/master_prompt.md)
und ist über die CLI per `sgsim brief` abrufbar. Wird automatisch vom
`AnthropicAIController` als System-Prompt geladen.

---

## Schreibstil

- Auf **Deutsch**, weil die Arbeit auf Deutsch entsteht.
- **Code-Identifier in Originalsprache** (Englisch), da sie genau so im
  Quellcode stehen.
- **Datei:Zeile-Referenzen** wo immer möglich, damit man im Code direkt
  hinspringen kann.
- **Kompakt** — kein Inhalt zweimal. Wenn etwas in zwei Dateien gehört, dann
  mit Querverweis.
