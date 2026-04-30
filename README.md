# sgsim — Smart-Grid-Simulator

CLI-gesteuerter Smart-Grid-Simulator als physikalisches Experiment fuer eine
Seminararbeit (Abitur, Physik). Untersucht wird, ob eine KI-basierte Steuerung
den Energieverbrauch und die Verluste im Vergleich zu einer regelbasierten
Steuerung senken kann.

## Installation

```bash
pip install -e .[dev]
```

## Schnellstart

```bash
# 1. Standard-Szenario laden (kleine Stadt mit PV + Wohnlast)
sgsim init

# 2. Einen Tag (96 Ticks à 15 min) ohne Eingriff durchlaufen
sgsim run --steps 96

# 3. Metriken anschauen
sgsim metrics

# 4. Vollstaendige Zeitreihe als CSV fuer die Auswertung exportieren
sgsim export --out tag1.csv
```

## Steuerung durch einen externen Controller (z. B. Claude)

Der Simulator ist zustandsbehaftet: `.sgsim_state.json` haelt den Netzzustand
zwischen CLI-Aufrufen. Ein Controller arbeitet damit so:

```bash
sgsim init
while [ "$(sgsim state | jq .step_count)" -lt 96 ]; do
    sgsim state                                        # Lage lesen
    sgsim set-curtailment pv_dachanlagen 0.2           # Eingriff
    sgsim tick                                          # einen Schritt vor
done
sgsim export --out claude_run.csv
```

## Tests

```bash
pytest
```

Die Tests pruefen physikalische Konsistenz (Energiebilanz, Persistenz,
Vorzeichenkonventionen) und sind die Vertrauensbasis fuer alle exportierten
Messwerte.

## Aktueller Stand (M1 + M2)

Implementiert:

- **Komponenten-Basis**: `Component`-ABC mit fester Vorzeichenkonvention,
  `snapshot()` fuer Zusatz-Logging, deserialisierbare Registry.
- **Lasten**: `ResidentialLoad` (BDEW-H0-aehnlich), `CommercialLoad` (G0),
  `IndustrialLoad` (L0).
- **Erneuerbare Erzeuger** (nicht dispatchierbar): `PVPlant`,
  `WindTurbine` (½ρAv³c_p mit Cut-in/Rated/Cut-out), `RunOfRiverHydro`.
- **Dispatchierbare Erzeuger**: `GasGuDPlant`, `CoalPlant`, `BiomassPlant`
  mit Sollwert, Rampen, P_min/P_max, Wirkungsgrad und CO2-Faktor.
- **Speicher**: `BatteryStorage`, `PumpedHydroStorage`
  (Geometrie-Konstruktor E = ρVgh), `HydrogenStorage`.
- **Wettermodell**: deterministisch ueber Seed (Strahlung, Wind, Temperatur).
- **Tick-Engine**: 15-min-Schritte, vollstaendige Mess-Logs inkl. CO2 und
  Erneuerbaren-Anteil, JSON-Persistenz.
- **CLI**: `init`, `state`, `tick`, `run`, `dispatch`, `set-curtailment`,
  `metrics`, `export` (CSV mit Pro-Komponenten- und SoC-Spalten).

## Steuerungs-Workflow fuer den Controller

```bash
sgsim init                            # Standardszenario stadt_mittel
sgsim state | jq .components          # was steht zur Verfuegung?
sgsim dispatch gas_kw 150             # Erzeuger-Sollwert (MW)
sgsim dispatch -- batterie_quartier -30   # Speicher laden (negativ)
sgsim dispatch pumpspeicher_alpental 100  # Speicher entladen
sgsim set-curtailment pv_aufdach 0.2  # PV abregeln
sgsim tick                            # 15 min vorwaerts
sgsim metrics                         # CO2, Erneuerbaren-Anteil, Brownouts
sgsim export --out tag.csv            # Auswertung
```

`--` vor negativen Werten ist noetig, damit Click sie nicht als Option liest.

## Experimente: Strategien gegeneinander laufen lassen

```bash
# Naive Baseline (statische fossile Sollwerte, kein Eingriff)
sgsim experiment run --controller naive --steps 96 --seed 42 \
                     --out results/naive.csv

# Regelbasierter Smart-Controller (Merit-Order + Speicherheuristik)
sgsim experiment run --controller rule_based --steps 96 --seed 42 \
                     --out results/rule_based.csv

# Vergleich (erste Datei = Baseline; Deltas in % zur Baseline)
sgsim experiment compare results/naive.csv results/rule_based.csv
```

Erste Vergleichszahlen aus dem Default-Szenario `stadt_mittel` (24 h, Seed 42):

| Metrik | Naive | RuleBased | Delta |
|---|---|---|---|
| Erzeugte Energie [MWh] | 11 161 | 5 827 | −47.8 % |
| CO₂ [t] | 7.30 | 4.33 | **−40.6 %** |
| CO₂ pro MWh Bedarf [kg] | 1 552 | 813 | **−47.6 %** |
| Surplus (verschwendet) [MWh] | 6 459 | 536 | **−91.7 %** |
| Brownout-Ticks | 0 | 24 | (siehe unten) |

Die regelbasierte Strategie reduziert Energieverschwendung und CO2 dramatisch,
hat aber 24/96 Brownout-Ticks (~25 % der Zeit) wegen der Anfahrtraegheit der
Kohle und der begrenzten Speicherreserven. Genau dieser Trade-off ist der
Spielraum, den die KI-Steuerung schliessen muss.

## Geplant (M4+)

- KI-Run-Skript: Schleife, in der Claude pro Tick Setpoints vergibt
  (CLI-Modus mit `.sgsim_state.json` ist dafuer bereits vollstaendig)
- Sektorkopplung: V2G-E-Auto-Flotte, Waermepumpe, Elektrolyseur
- Netzleitungen mit I²R-Verlusten, Frequenzmodell
- Echte Lastprofile (BDEW H0/G0/L0 als CSV), DWD-/PVGIS-Wetterdaten
- Statistische Auswertung mehrerer Seeds (Welch-t, Cohen's d), Plots
