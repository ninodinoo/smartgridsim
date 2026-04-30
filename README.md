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

## Geplant (M3+)

- Regelbasierter Controller (Merit-Order + einfache Speicherregel)
- KI-Run-Skript: Schleife, in der Claude pro Tick Setpoints vergibt
- Sektorkopplung: V2G-E-Auto-Flotte, Waermepumpe, Elektrolyseur
- Netzleitungen mit I²R-Verlusten, Frequenzmodell
- Echte Lastprofile (BDEW H0/G0/L0 als CSV), DWD-/PVGIS-Wetterdaten
- Statistische Auswertung mehrerer Laeufe (Welch-t, Cohen's d)
