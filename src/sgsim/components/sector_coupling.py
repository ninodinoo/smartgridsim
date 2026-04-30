"""Sektorkopplungs-Komponenten: steuerbare Lasten, die zusaetzliche
Stellgroessen fuer die KI-Steuerung im 100%-erneuerbaren System bieten.

Das Konzept der Sektorkopplung: Strom-, Waerme- und Mobilitaetssektor werden
nicht mehr getrennt versorgt, sondern dynamisch verknuepft. Damit lassen
sich Erzeugungsspitzen aufnehmen (Power-to-Heat, Power-to-Gas) und
Lasten verschieben (Wallbox-Steuerung).

Diese Komponenten sind aus Netzsicht **steuerbare Lasten** (Setpoint negativ
bzw. fuer V2G auch positiv) — die KI entscheidet pro Tick, wie viel sie
ziehen oder einspeisen.
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Component, TickContext


# ---------------------------------------------------------------------------
# Waermepumpen-Last mit thermischem Pufferspeicher
# ---------------------------------------------------------------------------

@dataclass
class HeatPumpLoad(Component):
    """Aggregat-Waermepumpe mit thermischem Gebaeudespeicher.

    Modell:
        thermische Bedarfsleistung Q [MW] folgt Aussentemperatur (Heizkurve)
        elektrische Bedarfsleistung P_baseline = Q / cop
        Gebaeudespeicher kann Q vor- oder nachladen → P kann zwischen 0 und
        einem Maximum (P_baseline * boost_factor) variieren.

    Steuerung:
        setpoint_mw [MW, positiv = Strombezug] — die elektrische Sollleistung,
        die die KI vorgibt. Die Engine wandelt sie in negative Wirkleistung
        am Knoten um. Effektiv ist die Komponente eine flexible Last:
            P_min = 0
            P_max = baseline * boost_factor
        Der thermische SoC (in MWh thermische Energie im Speicher) entwickelt
        sich gemaess: dE/dt = P*cop - Q.
        Wenn der Speicher leer (E ≤ 0) und P*cop < Q, nicht haltbar — als
        thermisches "Brownout" gezaehlt (separat von elektrischem Brownout).

    Vereinfachung: Heizkurve linear in der Temperatur, ueber 18°C kein Bedarf.
    """

    base_thermal_demand_mw: float = 30.0   # Bedarf bei 0°C
    cop: float = 3.5                       # COP einer Luft-Wasser-WP
    boost_factor: float = 2.0              # max P relativ zu Baseline
    thermal_capacity_mwh: float = 100.0    # Pufferspeicher (Gebaeudemasse)
    thermal_soc_mwh: float = 50.0          # aktueller thermischer Energieinhalt
    setpoint_mw: float = 0.0               # vom Controller gesetzt (positiv)

    def _thermal_demand_mw(self, ctx: TickContext) -> float:
        # Heizgrenze 18°C (DIN-typisch)
        if ctx.temperature_c >= 18.0:
            return 0.0
        # Linear: bei 0°C voller Bedarf, bei 18°C kein Bedarf
        scale = (18.0 - ctx.temperature_c) / 18.0
        return self.base_thermal_demand_mw * scale

    def step(self, dt_h: float, ctx: TickContext) -> float:
        baseline_p = self._thermal_demand_mw(ctx) / self.cop if self.cop > 0 else 0.0
        max_p = baseline_p * self.boost_factor

        # Sollwert clampen
        p = max(0.0, min(self.setpoint_mw, max_p))

        # thermische Bilanz (mit Realitaet abgleichen)
        q_in = p * self.cop * dt_h
        q_out = self._thermal_demand_mw(ctx) * dt_h
        new_soc = self.thermal_soc_mwh + q_in - q_out
        new_soc = max(0.0, min(self.thermal_capacity_mwh, new_soc))
        self.thermal_soc_mwh = new_soc

        return -p  # negative Wirkleistung am Knoten

    def snapshot(self) -> dict[str, float]:
        return {
            "setpoint_mw": self.setpoint_mw,
            "thermal_soc_mwh": self.thermal_soc_mwh,
            "thermal_soc_fraction": (
                self.thermal_soc_mwh / max(self.thermal_capacity_mwh, 1e-9)
            ),
        }


# ---------------------------------------------------------------------------
# E-Auto-Flotte mit V2G
# ---------------------------------------------------------------------------

@dataclass
class EVFleet(Component):
    """Aggregat-Modell einer E-Auto-Flotte mit Vehicle-to-Grid (V2G).

    Modell:
        n_vehicles Autos, jedes mit battery_kwh Akku und peak_charge_kw.
        Verfuegbarkeitsfaktor (am Netz angeschlossen) variiert ueber den Tag:
            06:00–18:00: nur away_fraction zu Hause (Pendler weg)
            sonst: 1 - away_fraction × 0.3 (auch nachts ein paar unterwegs)

    Steuerung:
        setpoint_mw — positiv = entladen (V2G), negativ = laden, 0 = idle.
        Limitiert durch verfuegbare Flotte * peak_charge_kw / 1000.
        Realer SoC wird nachgeführt, ist nicht verhandelbar (Akku).

    Vereinfachung: Mobilitaetsbedarf abstrakt als baseline_drive_kwh_per_day
    pro Auto modelliert (pauschal abgezogen).
    """

    n_vehicles: int = 5000
    battery_kwh: float = 60.0
    peak_charge_kw: float = 11.0          # Wallbox 11 kW
    eta_charge: float = 0.92
    eta_discharge: float = 0.92
    away_fraction: float = 0.7             # Anteil tagsueber unterwegs
    drive_kwh_per_day: float = 12.0        # ~50 km/Tag bei 24 kWh/100km
    soc_kwh_per_vehicle: float = 30.0      # initial halbvoll
    setpoint_mw: float = 0.0

    @property
    def total_capacity_mwh(self) -> float:
        return self.n_vehicles * self.battery_kwh / 1000.0

    @property
    def total_soc_mwh(self) -> float:
        return self.n_vehicles * self.soc_kwh_per_vehicle / 1000.0

    @property
    def total_peak_charge_mw(self) -> float:
        return self.n_vehicles * self.peak_charge_kw / 1000.0

    def _availability(self, ctx: TickContext) -> float:
        """Anteil der Autos, die am Netz angeschlossen sind."""
        h = ctx.hour_of_day
        if 6.0 <= h < 18.0:
            return 1.0 - self.away_fraction
        if 18.0 <= h < 19.0:
            # linear ramping back home
            return (1.0 - self.away_fraction) + self.away_fraction * (h - 18.0)
        if 5.0 <= h < 6.0:
            # leaving — linear out
            return 1.0 - self.away_fraction * (h - 5.0)
        return 1.0 - self.away_fraction * 0.3   # nachts ein paar weg

    def step(self, dt_h: float, ctx: TickContext) -> float:
        avail = self._availability(ctx)
        max_p = self.total_peak_charge_mw * avail

        sp = self.setpoint_mw
        # Mobilitaets-Verbrauch pro Tick (kontinuierlich)
        drive_loss_mwh = (self.n_vehicles * self.drive_kwh_per_day / 1000.0) * (dt_h / 24.0)
        soc_total = self.total_soc_mwh - drive_loss_mwh
        soc_total = max(0.0, soc_total)

        if sp > 0:
            # entladen ins Netz (V2G)
            avail_e = soc_total * self.eta_discharge / dt_h if dt_h > 0 else 0
            p = min(sp, max_p, max(0.0, avail_e))
            soc_total -= p / self.eta_discharge * dt_h if self.eta_discharge > 0 else 0
        elif sp < 0:
            free = max(0.0, (self.total_capacity_mwh - soc_total)
                       / max(self.eta_charge, 1e-9) / dt_h)
            p_charge = min(-sp, max_p, free)
            soc_total += p_charge * self.eta_charge * dt_h
            p = -p_charge
        else:
            p = 0.0

        # SoC zurueck pro Fahrzeug
        if self.n_vehicles > 0:
            self.soc_kwh_per_vehicle = soc_total * 1000.0 / self.n_vehicles

        return p

    def snapshot(self) -> dict[str, float]:
        return {
            "setpoint_mw": self.setpoint_mw,
            "soc_kwh_per_vehicle": self.soc_kwh_per_vehicle,
            "soc_fraction": self.soc_kwh_per_vehicle / max(self.battery_kwh, 1e-9),
        }


# ---------------------------------------------------------------------------
# Elektrolyseur (Power-to-Gas)
# ---------------------------------------------------------------------------

@dataclass
class Electrolyzer(Component):
    """Elektrolyseur: nimmt Strom auf, produziert Wasserstoff.

    Vereinfachung: hier nur als steuerbare Last modelliert. Der erzeugte
    Wasserstoff wird NICHT direkt in einen H2-Speicher gebucht (das wuerde
    eine Komponenten-Kopplung erfordern). Statt dessen ist der
    Elektrolyseur ein "Stromschlucker", der CO2-frei ist und im Modell
    Ueberschuss aufnehmen kann.

    Wer den H2-Output explizit modellieren will, kann eine Sub-Klasse
    schreiben, die das HydrogenStorage-Objekt referenziert.
    """

    p_max_mw: float = 50.0
    eta_h2: float = 0.70                  # informativ, nicht in Bilanz
    setpoint_mw: float = 0.0              # positiv = Strombezug

    def step(self, dt_h: float, ctx: TickContext) -> float:
        p = max(0.0, min(self.setpoint_mw, self.p_max_mw))
        return -p

    def snapshot(self) -> dict[str, float]:
        return {"setpoint_mw": self.setpoint_mw}
