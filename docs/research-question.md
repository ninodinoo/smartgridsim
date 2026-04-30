# Forschungsfrage der Seminararbeit

## Titel-Vorschlag

> *"Versorgungssicherheit in einem 100 %-erneuerbaren Stromsystem:
> Kann eine LLM-basierte Steuerung regelbasierte Heuristiken übertreffen?"*

## Hintergrund

Die Energiewende erfordert ein Stromsystem, das **ohne fossile Reserven**
auskommt. Klassische Smart-Grid-Steuerungen sind regelbasierte Heuristiken
(Merit-Order-Dispatch, Speicher-Ampelregeln). Ihre Leistungsfähigkeit ist
gut dokumentiert in fossilen Mixen, aber **in einem 100 %-erneuerbaren
System mit volatilen Quellen wird Versorgungssicherheit zur eigentlichen
Herausforderung** — nicht mehr CO₂-Reduktion.

Große Sprachmodelle (LLMs wie Claude) können in offenen Entscheidungssitua-
tionen flexibel reagieren und mehrere Schritte vorausplanen. Es ist offen,
ob diese Eigenschaft für Echtzeit-Netzsteuerung ausreicht und Mehrwert
gegenüber etablierten Heuristiken bringt.

## Hypothese

**H1:** Eine LLM-basierte Steuerung senkt im 100 %-erneuerbaren System die
Anzahl der Brownout-Ticks (Versorgungsausfälle) gegenüber einer
regelbasierten Steuerung um mindestens 30 %, ohne dass CO₂-Emissionen oder
Energieverschwendung signifikant steigen.

**H0 (Nullhypothese):** Es gibt keinen signifikanten Unterschied zwischen
LLM- und regelbasierter Steuerung in den Hauptmetriken.

## Experimentalaufbau

### Unabhängige Variable
Steuerungsstrategie:
- `naive` (statische Sollwerte) — untere Vergleichsgrenze
- `rule_based` (Merit-Order + Speicher-Heuristik) — Hauptvergleich
- `random_ai` — Sanity-Check
- LLM (Anthropic-API mit `claude-haiku-4-5` oder Claude-Code-Subagents)

### Abhängige Variablen (Messgrößen aus jedem 24-h-Lauf)

| Größe | Messmethode |
|---|---|
| Versorgungssicherheit | `brownout_steps` (Anzahl Ticks mit `P_total < 0`) |
| nicht gedeckte Energie | `unserved_energy_mwh` |
| Spitzendefizit | `peak_deficit_mw` |
| Frequenzabweichung | `max_frequency_deviation_hz`, Ticks außerhalb ±0.2 Hz |
| CO₂-Emissionen | `co2_kg` |
| Energieverschwendung | `surplus_energy_mwh` |
| Erneuerbaren-Anteil | `renewable_share_of_demand` |
| Wirtschaftlichkeit | `lcoe_eur_per_mwh`, `voll_cost_eur` |

### Kontrollvariablen
- **Identisches Szenario** `stadt_mittel.yaml` für alle Strategien
- **Identische Seeds** zwischen Strategien (paarweise Vergleichbarkeit)
- **Identische Anzahl Ticks** (96 = 24 h)
- **Reproducibility-Hash** in jeder `metrics.json` als Audit-Trail

### Stichprobengröße
- Pilotlauf: n = 3–5 Seeds (Plausibilitätsprüfung)
- Hauptauswertung: **n = 30 Seeds** je Strategie
- Begründung: Welch-t-Test bei moderater Streuung benötigt n ≥ 30 für
  zuverlässige Signifikanzaussage; mit dem Skript
  `compare_strategies.py` läuft das in wenigen Minuten lokal.

### Statistische Auswertung

- **Welch-t-Test** zwischen LLM und regelbasiert für jede Hauptmetrik
- **Cohen's d** als Effektstärke (|d| ≥ 0.5 mittel, ≥ 0.8 groß)
- **Bootstrap-Konfidenzintervalle** für Mediane (optional, gegen Ausreißer)
- **Visualisierung** als Boxplots aus den Per-Run-Daten

### Pre-Registration
Die Hypothese H1 und die Hauptmetrik (`brownout_steps`) sind **vor** den
LLM-Läufen festgelegt — diese Datei selbst ist die Pre-Registration.
Damit ist Cherry-Picking ausgeschlossen.

## Mögliche Ergebnisse und ihre Interpretation

| Ergebnis | Interpretation |
|---|---|
| LLM senkt Brownouts signifikant, kein CO₂-Anstieg | **H1 bestätigt** — LLM-Steuerung ist eine vielversprechende Technologie für die Energiewende |
| LLM senkt Brownouts, aber CO₂ steigt deutlich | Trade-off-Diskussion erforderlich; LLM nutzt H₂-Backup zu früh |
| Keine Verbesserung, höhere Streuung | LLM-Antworten zu unzuverlässig für sicherheitskritische Echtzeit-Steuerung |
| LLM schlechter als regelbasiert | **H0 bestätigt** — Heuristiken sind ausreichend; LLM-Komplexität rechtfertigt sich nicht |

Jedes dieser Ergebnisse ist publikations- bzw. seminarwürdig.

## Bekannte Limitationen (für die Diskussion)

Siehe vollständige Auflistung in [`methodology.md`](methodology.md). Wichtigste:

1. **Synthetisches Wetter und BDEW-approximierte Lastprofile** — nicht
   real-validiert. Mit `CsvWeather`/`CsvProfileLoad` lassen sich echte Daten
   einbinden, sobald verfügbar.
2. **Kupferplatten-Topologie** — kein Lastfluss, keine Engpässe.
3. **Perfect-foresight-Forecast** für `rule_based` — bevorteilt die
   Heuristik. Mit `forecast.noisy_forecast()` korrigierbar.
4. **n = 1 LLM-Lauf pro Konversation** bei Live-Steuerung — Statistik nur
   über API-Skript (`compare_strategies.py` mit `anthropic_ai`) oder
   Subagent-Pool.

## Verwandte Doku

- [`methodology.md`](methodology.md) — Modell-Annahmen
- [`experiments.md`](experiments.md) — wie führt man die Auswertung durch
- [`controllers.md`](controllers.md) — was machen die Strategien genau
- [`claude_live_run_seed42.md`](claude_live_run_seed42.md) — erster Live-Lauf
  (für das alte fossile Modell, historisch)
