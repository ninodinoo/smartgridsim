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

## Aktueller Stand (M1+M3)

Implementiert:

- Komponenten-Basis (`Component`-ABC, Vorzeichenkonvention, Registry)
- Zwei konkrete Komponenten: `PVPlant`, `ResidentialLoad`
- Synthetisches Wettermodell (deterministisch ueber Seed)
- Tick-Engine mit 15-min-Aufloesung, Tick-Protokoll, JSON-Persistenz
- CLI: `init`, `state`, `tick`, `run`, `set-curtailment`, `metrics`, `export`

Geplant (M2+):

- Wind, Wasserkraft, Biomasse, Gas-GuD, Kohle, KWK
- Batterie-, Pumpspeicher-, H2-Speicher (`Storage`-Hierarchie)
- E-Mobilitaet (V2G), Waermepumpen, Demand Response
- Netzleitungen mit I^2R-Verlusten, Frequenzmodell
- Echte Lastprofile (BDEW H0/G0/L0), DWD-Wetterdaten
- Regelbasierter Controller + KI-Run-Skript
- Statistische Auswertung mehrerer Laeufe
