# Komponenten-Referenz

Alle Netzteilnehmer mit Physik-Modell, Parametern und Konventionen.
Implementiert in `src/sgsim/components/`.

## Vorzeichenkonvention der Wirkleistung [MW]

| Komponententyp | Vorzeichen | Bedeutung |
|---|---|---|
| Erzeuger (PV, Wind, Bio, …) | **P > 0** | speist ins Netz ein |
| Lasten (Wohnen, Gewerbe, Industrie) | **P < 0** | entnimmt aus dem Netz |
| Speicher (Batterie, Pumpspeicher, H₂) | **P > 0** = entladen, **P < 0** = laden |
| Sektorkopplungs-Lasten (HeatPump, Electrolyzer) | **P < 0** | wie eine Last |
| EV-Flotte (V2G) | **P > 0** = entladen, **P < 0** = laden |

Energie [MWh] = P [MW] × dt [h]. Bei dt = 0.25 h (15 min) entsprechen
100 MW Bezug also 25 MWh pro Tick.

---

## Lasten (`loads.py`)

### `ResidentialLoad` — BDEW-H0-Approximation

Wohngebiet mit Doppel-Spitze:

$$P(h) = -\Big(\text{base} + \text{peak} \cdot \max\big(g(h, 7), g(h, 19)\big)\Big)$$

mit $g(h, h_0) = e^{-(h-h_0)^2 / \sigma^2}$. Default Standardszenario:
`base=60`, `peak=90` MW, also Min ~60 MW (Nacht), Max ~150 MW (7:00 / 19:00).

### `CommercialLoad` — BDEW-G0

Plateau 8–18 Uhr mit linearen Flanken 6–8 und 18–20.
`base=10`, `peak=70` MW. Außerhalb des Plateaus 0.

### `IndustrialLoad` — BDEW-L0

Praktisch konstante Last mit Nachtreduktion (22–6 Uhr).
`base=60` MW, `night_reduction=0.20`. Tag 60 MW, Nacht 48 MW.

### `CsvProfileLoad` — Drop-in für reale Daten

Liest 15-min-Profile aus CSV (`hour_of_day,relative_load`), interpoliert
linear, skaliert auf `peak_mw`. Drop-in-Ersatz für die obigen Klassen.

---

## Erneuerbar nicht-dispatchierbar (`renewables.py`)

### `PVPlant`

$$P_{el} = G \cdot A \cdot \eta_{module} \cdot \eta_{inv} \cdot (1 - c)$$

mit $G$ = Globalstrahlung [W/m²], $A$ = Modulfläche [m²], $c$ = Curtailment
(0..1). Default-Wirkungsgrade: Modul 20 % (Si), Wechselrichter 97 %.

Im Default-Szenario: 1 000 000 m² (= 100 ha, ~200 MWp). Realer Peak bei
Standardbewölkung (`cloudiness=0.4`) ~110 MW.

### `WindTurbine`

Drei Regime nach Datenblatt-Konvention:
$$P(v) = \begin{cases}
0 & v < v_{cut\_in} \text{ oder } v \ge v_{cut\_out} \\
\tfrac{1}{2} \rho A v^3 c_p \le P_{rated} & v_{cut\_in} \le v < v_{rated} \\
P_{rated} & v_{rated} \le v < v_{cut\_out}
\end{cases}$$

Mit $A = \pi (D/2)^2$, $c_p$ unter dem Betz-Limit (16/27 ≈ 0.593).

Default: Onshore-Park 12 × 4 MW, $c_p$ = 0.42, $v_{rated}$ = 12 m/s.
Offshore-Anteil: 5 × 10 MW, $c_p$ = 0.48, $v_{rated}$ = 11 m/s.

### `RunOfRiverHydro`

Quasi-konstante Einspeisung: $P = P_{nom} \cdot \text{availability}$.
Default: 12 MW × 0.95 = 11.4 MW. Saisonale Variation nicht modelliert.

---

## Erneuerbar dispatchierbar (`dispatchable.py`)

Alle erben von `DispatchableGenerator` und folgen einer Setpoint-Logik mit
Rampen-Limit:

```
delta_max  = ramp_mw_per_min · dt_min
delta      = clip(setpoint - current, -delta_max, +delta_max)
current_p  = clip(current + delta, p_min, p_max)
```

CO₂-Buchhaltung: $\text{CO}_2[\text{kg}] = P[\text{MW}] \cdot dt[\text{h}] \cdot f_{CO_2}[\text{kg/MWh}]$.

| Klasse | P_min | P_max | η | f_CO₂ kg/MWh | Ramp MW/min |
|---|---|---|---|---|---|
| `BiomassPlant` | 5 | 25 | 0.35 | 25 | 0.5 |
| `GeothermalPlant` | 1 | 8 | 0.12 | 30 | 0.3 |
| `HydrogenGasTurbine` | 20 | 200 | 0.55 | 5 | 8.0 |

**Wichtige Modell-Eigenheit:** Wenn `setpoint < p_min`, schaltet die Engine
sofort auf 0. Reales Anfahren würde Stunden dauern — siehe Vereinfachungen
in [`methodology.md`](methodology.md).

---

## Speicher (`storage.py`)

### Generelle Mechanik (`Storage` ABC)

Setpoint-Vorzeichen: `> 0` entladen, `< 0` laden. Energiebuchhaltung
mit Wirkungsgraden:

- Laden ($P < 0$): in den Speicher gelangen $|P| \cdot \eta_{charge} \cdot dt$ MWh
- Entladen ($P > 0$): aus dem Speicher entnommen werden $P / \eta_{discharge} \cdot dt$ MWh
- Round-Trip-Wirkungsgrad: $\eta_{rt} = \eta_{charge} \cdot \eta_{discharge}$

Begrenzungen: `|P| ≤ p_max_charge_mw` bzw. `p_max_discharge_mw`,
`min_soc_mwh ≤ soc_mwh ≤ capacity_mwh`.

### `BatteryStorage` — Li-Ion-Quartiersbatterie

Default: `capacity_mwh=200`, `±100 MW`, $\eta_{rt} = 0.90$, `min_soc=20 MWh`
(10 % für Lebensdauer).

### `PumpedHydroStorage`

$$E_{pot}[\text{J}] = \rho_{water} \cdot V \cdot g \cdot h \quad
\Rightarrow \quad E[\text{MWh}] = E_{pot} / 3.6 \cdot 10^9$$

Klassmethode `from_geometry()` baut die Komponente aus Fallhöhe, Volumen
und Leistung. Default: 200 m Fallhöhe × 1.8 Mio m³ ≈ **980 MWh**, 200/220 MW
Lade-/Entladeleistung, $\eta_{pump}$ 0.88, $\eta_{turbine}$ 0.91 ($\eta_{rt}$ 0.80).

### `HydrogenStorage` — saisonal

Power-to-Gas-to-Power: Elektrolyseur ($\eta$ 0.65) lädt H₂ ein, Brennstoffzelle
oder H₂-GuD ($\eta$ 0.55) wandelt zurück. **Round-Trip nur 0.36** — ineffizient,
aber als einzige Form Tage- bis Wochen-Speicher.

Default: 5 000 MWh (~1.5 Wochen Vollversorgung), 100/150 MW.

---

## Sektorkopplung (`sector_coupling.py`)

Steuerbare Lasten als zusätzliche Stellgrößen für die KI.

### `HeatPumpLoad`

Aggregat-Wärmepumpe mit thermischem Pufferspeicher (Gebäudemasse).

- Thermischer Bedarf folgt Außentemperatur (Heizgrenze 18 °C, lineare Kurve)
- Elektrische Baseline: $P_{el} = Q_{th} / \text{COP}$ mit COP 3.5
- Setpoint kann von 0 bis $P_{el} \cdot \text{boost\_factor}$ variieren
- Thermischer SoC: $\frac{dE_{th}}{dt} = P_{el} \cdot \text{COP} - Q_{th,demand}$

Default: 30 MW thermischer Bedarf bei 0 °C, 100 MWh thermischer Puffer.

### `EVFleet` — Vehicle-to-Grid

5 000 Autos × 60 kWh Akku, 11 kW Wallbox.
- Verfügbarkeit: 70 % weg 6:00–18:00 Uhr
- Mobilitätsbedarf: pauschal 12 kWh/Tag pro Auto
- Setpoint > 0 = entladen ins Netz (V2G), < 0 = laden, $\eta$ = 0.92

Aggregierte Spitzenleistung: 55 MW (5000 × 11 kW).

### `Electrolyzer` — Power-to-Gas

Reine Last (50 MW max), $\eta_{H_2}$ = 0.70 (informativ; H₂-Output ist
**nicht** an `HydrogenStorage` gekoppelt — Vereinfachung, siehe Methodology).

---

## CO₂-Faktoren (Quellen für die Seminararbeit)

| Erzeuger | Faktor [kg/MWh_el] | Quelle |
|---|---|---|
| Biomasse | 25 | Bilanz-neutral, Logistik-Restemissionen |
| Geothermie | 30 | Begleitgase + Hilfsstrom |
| H₂-Gasturbine | 5 | direkt am Schornstein (ohne H₂-Vorkette) |
| Gas-GuD (nicht im Default) | 350 | Umweltbundesamt 2023 |
| Steinkohle (nicht im Default) | 900 | UBA 2023 |

**Bewusst nicht modelliert:** Lebenszyklus-Emissionen (Bau, Brennstoffkette,
Rückbau). Siehe [`methodology.md`](methodology.md) §4.

---

## Komponente registrieren — wie funktioniert das?

Alle obigen Klassen sind in `COMPONENT_REGISTRY` (Datei
`components/__init__.py`) eingetragen, sodass sie aus YAML-Szenarien
deserialisierbar sind. Eigene Komponenten anlegen: siehe
[`dev/extending.md`](dev/extending.md).
