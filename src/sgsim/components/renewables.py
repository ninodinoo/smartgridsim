"""Fluktuierende erneuerbare Erzeuger (PV, Wind).

Diese Komponenten sind nicht dispatchierbar — ihre Leistung folgt dem Wetter.
Eingriffsmoeglichkeit fuer den Controller ist die Abregelung (`curtailment`,
0..1), zur Modellierung von "Ueberschuss verwerfen, weil nichts mehr aufnimmt".
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Component, TickContext


@dataclass
class PVPlant(Component):
    """Photovoltaik-Anlage.

    Modell:  P = G * A * eta_module * eta_inverter
    G = Globalstrahlung [W/m^2], A = Modulflaeche [m^2].
    Skaliert auf MW: P[MW] = G * A * eta / 1e6.
    """

    area_m2: float
    eta_module: float = 0.20          # typische Si-Module 18-22 %
    eta_inverter: float = 0.97
    curtailment: float = 0.0          # 0..1, vom Controller gesetzt

    def step(self, dt_h: float, ctx: TickContext) -> float:
        p_w = ctx.irradiance_w_m2 * self.area_m2 * self.eta_module * self.eta_inverter
        p_mw = p_w / 1e6
        return p_mw * (1.0 - self.curtailment)

    def snapshot(self) -> dict[str, float]:
        return {"curtailment": self.curtailment}


@dataclass
class WindTurbine(Component):
    """Windkraftanlage mit physikalischer Leistungskurve.

    P_aero = 0.5 * rho * A * v^3 * c_p   (kinetische Leistung des Windes
    multipliziert mit dem Leistungsbeiwert; Betz-Limit c_p_max = 16/27 ≈ 0.593,
    real moderne WEA c_p ≈ 0.40–0.50).

    Drei Regime nach Datenblatt-Konvention:
        v < v_cut_in            → P = 0  (Anlauf erst ab Mindestwind)
        v_cut_in ≤ v < v_rated  → P = aerodynamisches Modell, capped bei P_rated
        v_rated ≤ v < v_cut_out → P = P_rated
        v ≥ v_cut_out           → P = 0  (Sturmabschaltung zum Schutz)
    """

    rotor_diameter_m: float
    p_rated_mw: float
    n_turbines: int = 1
    cp: float = 0.42                  # realistischer Leistungsbeiwert
    v_cut_in: float = 3.0             # m/s
    v_rated: float = 12.0
    v_cut_out: float = 25.0
    air_density_kg_m3: float = 1.225  # Standardatmosphaere
    curtailment: float = 0.0

    def _power_per_turbine_mw(self, v: float) -> float:
        if v < self.v_cut_in or v >= self.v_cut_out:
            return 0.0
        if v >= self.v_rated:
            return self.p_rated_mw
        import math
        area = math.pi * (self.rotor_diameter_m / 2.0) ** 2
        p_w = 0.5 * self.air_density_kg_m3 * area * v ** 3 * self.cp
        p_mw = p_w / 1e6
        return min(p_mw, self.p_rated_mw)

    def step(self, dt_h: float, ctx: TickContext) -> float:
        per_turbine = self._power_per_turbine_mw(ctx.wind_speed_m_s)
        return per_turbine * self.n_turbines * (1.0 - self.curtailment)

    def snapshot(self) -> dict[str, float]:
        return {"curtailment": self.curtailment}


@dataclass
class RunOfRiverHydro(Component):
    """Laufwasserkraftwerk — naeherungsweise konstante Einspeisung mit
    schwacher saisonaler Variation. Vereinfachung: hier zeitlich konstant,
    spaeter durch Pegelstands-Zeitreihe ersetzbar."""

    p_mw: float
    availability: float = 0.95        # Verfuegbarkeit (Wartung, Niedrigwasser)

    def step(self, dt_h: float, ctx: TickContext) -> float:
        return self.p_mw * self.availability
