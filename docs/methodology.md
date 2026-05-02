# Methodologie und Modell-Annahmen

Diese Datei dokumentiert alle wesentlichen Vereinfachungen, Annahmen und
Datenquellen des Simulationsmodells. Sie ist die zentrale Verteidigungs-
linie der Seminararbeit gegen Kritik an einzelnen Stellen.

## 1. Räumliche und zeitliche Auflösung

- **Räumlich:** ein einziger Sammelknoten (Kupferplatte). Es gibt **keine
  Übertragungsleitungen mit Verlusten oder Kapazitätsgrenzen**. Alle
  Erzeuger und Verbraucher sind direkt verbunden. → Ergebnisse stellen eine
  obere Schranke der Steuerbarkeit dar; ein Real-Netz mit Engpässen wäre
  schwerer zu steuern.
- **Zeitlich:** 15-Minuten-Schritte (96 pro Tag). Standard in der Energie-
  wirtschaft (Bilanzkreisabrechnung). Sub-Sekunden-Phänomene (Frequenz-
  schwankungen, Stoßlast) sind damit nicht aufgelöst.

## 2. Wettermodell (`src/sgsim/weather.py`)

- **Synthetisch**, nicht aus realen Messreihen.
- Globalstrahlung als Sinusbogen 6:00–20:00 Uhr, gedämpft mit `cloudiness`,
  überlagert mit ±5 % deterministischem Rauschen.
- Wind: Mittelwert ± diurnale Schwankung ± Rauschen, untere Schranke 0.
- Temperatur: cosinusförmiger Tagesgang um Mittelwert.
- **Reproduzierbar** über `seed`: Wetterwerte sind reine Funktionen von
  `(seed, sim_time_h, Variable)`, damit Forecasts, Snapshots und
  Speichern/Laden die Zeitreihe nicht verändern.
- **Empfehlung**: für die Arbeit DWD-Stundenwerte oder PVGIS einsetzen
  (CSV-Schnittstelle steht in Phase 4 bereit).

## 3. Lastprofile (`src/sgsim/components/loads.py`)

- **`ResidentialLoad`** approximiert BDEW-H0: zwei Glockenkurven um 7:00
  und 19:00 Uhr.
- **`CommercialLoad`** approximiert BDEW-G0: Plateau 8:00–18:00 mit linearen
  Flanken.
- **`IndustrialLoad`** approximiert BDEW-L0: ~konstant mit Nachtreduktion.
- **Vereinfachung:** keine saisonale, Wochentag- oder Wetter-Abhängigkeit
  der Lasten. Real wäre die Last temperaturabhängig (Wärmebedarf) und
  würde an Wochenenden anders aussehen.
- **Empfehlung:** echte 15-min-BDEW-Profile als CSV einbinden (Schnittstelle
  in Phase 4).

## 4. Erzeuger-Modelle

### PV (`PVPlant`)
- $P = G \cdot A \cdot \eta_{module} \cdot \eta_{inverter}$
- Standard: Module 20 % Si-Wirkungsgrad, Wechselrichter 97 %.
- **Vereinfachung:** keine Temperaturabhängigkeit der Modulleistung
  (real fällt η bei hoher Modul-Temperatur), keine Verschattung,
  keine Ausrichtung (alle Module horizontal).

### Wind (`WindTurbine`)
- $P_{aero} = \tfrac{1}{2}\rho A v^3 c_p$, capped bei $P_{rated}$.
- Drei Regime: Cut-in / Teillast / Rated / Cut-out.
- $c_p$ unter Betz-Limit (16/27 ≈ 0.593); Onshore 0.42, Offshore 0.48.
- **Vereinfachung:** identische Windgeschwindigkeit über den ganzen Park
  (kein Wake-Effekt), konstante Luftdichte 1.225 kg/m³.

### Laufwasserkraft (`RunOfRiverHydro`)
- Konstante Einspeisung × Verfügbarkeitsfaktor (0.95).
- **Vereinfachung:** keine saisonale Variation des Pegelstandes.

### Biomasse (`BiomassPlant`), Geothermie (`GeothermalPlant`), H₂-Gasturbine (`HydrogenGasTurbine`)
- Dispatchierbar mit Sollwert, P_min, P_max, Rampe, Wirkungsgrad, CO₂-Faktor.
- **Vereinfachung der Rampen-Logik:** wenn der Setpoint unter P_min fällt,
  schaltet die Engine sofort auf 0 ab. Real braucht ein Kraftwerk mehrere
  Stunden zum An-/Ausfahren mit Mindestbetriebszeiten.
- **H₂-Kopplung:** die H₂-Gasturbine entnimmt pro Tick
  $P_{el} / \eta \cdot \Delta t$ chemische Energie aus dem saisonalen
  `HydrogenStorage`. Ist der Speicher auf Mindest-SoC, wird die elektrische
  Leistung der Turbine begrenzt.

### CO₂-Faktoren

Direktemissionen am Schornstein, Quellen: Umweltbundesamt 2023,
Fraunhofer ISE.

| Erzeuger | CO₂ kg/MWh_el |
|---|---|
| Biomasse | 25 (Bilanz neutral, Logistik-Restemissionen) |
| Geothermie | 30 (Begleitgase + Hilfsstrom) |
| H₂-Gasturbine | 5 (am Schornstein, ohne Vorkette) |

**Bewusst nicht modelliert:** Lebenszyklus-Emissionen (Bau, Brennstoffkette,
Rückbau). Eine Vollbilanz würde die Reihenfolge der Erzeuger ändern (PV-
Lebenszyklus ~40 kg/MWh, Wind ~10 kg/MWh, H₂ aus Erdgas-Reformierung wäre
gar nicht erneuerbar). Für die Steuerungsfrage spielt das keine Rolle.

## 5. Speicher-Modelle

- **`BatteryStorage`** (Li-Ion-Aggregat): η_charge = η_discharge = 0.95
  (η_rt 0.90), C-Rate 0.5, Mindest-SoC 10 % für Lebensdauer.
- **`PumpedHydroStorage`**: $E = \rho V g h$ (potentielle Energie),
  η_pump 0.88, η_turbine 0.91 (η_rt ≈ 0.80).
- **`HydrogenStorage`**: η_charge 0.65 (Elektrolyse), η_discharge 0.55
  (Brennstoffzelle / H₂-GuD), η_rt ≈ 0.36 — ineffizient, aber saisonal.

**Vereinfachungen:**
- Keine Selbstentladung (real bei Li-Ion ~2 %/Monat).
- Keine Alterung der Wirkungsgrade.
- Keine Lade-/Entlade-Verluste in Abhängigkeit von Auslastung (η ist
  realistisch C-Rate-abhängig).

## 6. Sektorkopplungs-Komponenten

### `HeatPumpLoad`
- Aggregat-Wärmepumpe mit thermischem Gebäudespeicher.
- COP konstant 3.5 (real temperaturabhängig: Luft-Wasser-WP fällt auf ~2.0
  bei -10 °C).
- Heizgrenze 18 °C, lineare Heizkurve.
- Thermischer Speicher 100 MWh als Puffer.

### `EVFleet`
- Aggregat-Modell: 5000 Autos mit je 60 kWh, 11 kW Wallbox.
- Verfügbarkeit: 70 % der Autos tagsüber 6:00–18:00 unterwegs.
- Mobilitätsbedarf pauschal 12 kWh/Tag pro Auto.
- **Vereinfachung:** keine individuellen Fahrprofile, kein Mindest-SoC für
  Abfahrt am Morgen.

### `Electrolyzer`
- Steuerbare Last (Strom → H₂), 50 MW max.
- η_h2 = 0.70. Die Engine bucht den erzeugten Wasserstoff in den saisonalen
  `HydrogenStorage`; ist dieser voll, wird die elektrische Last des
  Elektrolyseurs begrenzt.

## 7. Bilanzlogik der Engine

- Der Tick berechnet $P_{total} = \sum P_i$ über alle Komponenten.
- Bei $P_{total} > 0$: **Surplus** (Erzeugung > Last+Speicher-Aufnahme),
  Energie wird "verworfen" (kein automatisches Curtailment).
- Bei $P_{total} < 0$: **Defizit / Brownout**, Energie kann nicht gedeckt
  werden, wird in `unserved_energy_mwh` und `brownout_steps` gezählt.
- **Wichtig:** die Engine erzwingt **keine Bilanz** über einen Slack-Generator.
  Der Controller muss die Bilanz herstellen.

## 8. Steuerung

### `RuleBasedController`-Forecast
- Nutzt **perfect foresight** für den nächsten Tick: ruft `step()` der
  passiven Komponenten (Lasten, PV, Wind, Hydro) mit dem **echten** nächsten
  TickContext auf.
- Real hätte ein Controller nur ein verrauschtes Forecast-Modell. Diese
  Vereinfachung **bevorteilt rule_based**. → in Phase 4 als Forecast-
  Rauschen ergänzbar.

### KI-Steuerung
- LLM (Claude) bekommt einen JSON-Snapshot via `grid_snapshot()`.
- Antwortet mit JSON-Action-Dict via `apply_action()`.
- **Limitation:** Strategiewahl des LLM ist nicht vollständig deterministisch
  (auch bei Temperature 0 leichte Streuung).

## 9. Reproduzierbarkeit

- Alle Läufe sind über `--seed` reproduzierbar.
- Tests prüfen `Grid.save()` / `Grid.load()` Round-Trip inklusive identischem
  Folgetick und idempotente Wetterabfragen.
- **Empfehlung:** Reproducibility-Hash über Code-Version + Szenario + Seed
  in jedem CSV-Sidecar speichern (Phase 5).

## 10. Hauptthese der Arbeit

**Im 100 %-erneuerbaren Stromsystem ist Versorgungssicherheit (Brownouts)
die schwierige Größe, nicht CO₂.** Die Hypothese ist, dass eine LLM-basierte
Steuerung Brownouts gegenüber regelbasierten Heuristiken senken kann, indem
sie:

1. **Vorausschauend Speicher bewirtschaftet** (Pumpspeicher vor erwarteter
   Lastspitze laden, statt reaktiv).
2. **Sektorkopplung dynamisch nutzt** (HeatPump in Surplus boosten, V2G in
   Defizit aktivieren).
3. **Den H₂-Speicher gezielt für Dunkelflauten reserviert**, nicht
   alltäglich entlädt.

Diese Hypothese ist wissenschaftlich neu und hochrelevant für die
Energiewende.

## 11. Bekannte Schwächen für die Verteidigung

| Schwäche | Workaround in der Arbeit |
|---|---|
| Synthetisches Wetter | "Für Validierungsläufe würden DWD-Stundenwerte verwendet" |
| BDEW-Approximation | "Approximation auf Basis publizierter H0/G0/L0-Charakteristik" |
| Kupferplatte | "Annahme starkes Verteilnetz, Engpassmodellierung außerhalb des Scopes" |
| Perfect-foresight-Forecast | "Identisch für alle Strategien — fairer Vergleich" |
| H₂-Kopplung vereinfacht | "Ein gemeinsamer saisonaler H₂-Speicher, keine räumliche Gasnetz- oder Druckdynamik" |
| n=1 Lauf je Strategie | "Bootstrapping mit n≥30 Seeds in Anhang X" |
