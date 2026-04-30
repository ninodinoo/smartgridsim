"""Dispatchierbare (regelbare) thermische Erzeuger.

Diese Erzeuger besitzen einen Sollwert (`setpoint_mw`), den ein Controller
extern vorgibt. Der tatsaechliche Output folgt dem Sollwert mit physikalischer
Traegheit (Rampen-Limit) und respektiert technische Mindest- und Maximalwerte.

Modellannahmen pro Tick (Dauer dt):
    delta_max  = ramp_mw_per_min * dt_min
    delta      = clip(setpoint - current, -delta_max, +delta_max)
    current_p  = clip(current + delta, p_min_mw, p_max_mw)

Brennstoff- und CO2-Buchhaltung:
    fuel_mwh   = current_p * dt / eta            (Primaerenergie)
    co2_kg     = current_p * dt * co2_kg_per_mwh (auf elektrische Energie bezogen)
"""

from __future__ import annotations

from dataclasses import dataclass

from .base import Component, TickContext


@dataclass
class DispatchableGenerator(Component):
    """Basis fuer thermische Erzeuger mit Sollwert + Rampen + Wirkungsgrad."""

    p_min_mw: float
    p_max_mw: float
    ramp_mw_per_min: float
    eta: float                        # elektrischer Wirkungsgrad
    co2_kg_per_mwh: float             # Emissionsfaktor je MWh_el
    fuel: str = "generic"
    setpoint_mw: float = 0.0          # vom Controller gesetzt
    current_p_mw: float = 0.0         # interner Zustand zwischen Ticks

    def _follow_setpoint(self, dt_h: float) -> float:
        dt_min = dt_h * 60.0
        target = self.setpoint_mw
        if target > 0.0:
            target = min(max(target, self.p_min_mw), self.p_max_mw)
        elif target == 0.0:
            target = 0.0
        else:
            target = 0.0  # negative Sollwerte sind hier sinnlos
        delta_max = self.ramp_mw_per_min * dt_min
        delta = max(-delta_max, min(delta_max, target - self.current_p_mw))
        new_p = self.current_p_mw + delta
        # falls schon unter p_min, Rampe durfte 0 erlauben
        if new_p > 0.0 and new_p < self.p_min_mw:
            new_p = self.p_min_mw if delta > 0.0 else 0.0
        new_p = max(0.0, min(new_p, self.p_max_mw))
        self.current_p_mw = new_p
        return new_p

    def step(self, dt_h: float, ctx: TickContext) -> float:
        return self._follow_setpoint(dt_h)

    def snapshot(self) -> dict[str, float]:
        p = self.current_p_mw
        return {
            "setpoint_mw": self.setpoint_mw,
            "current_p_mw": p,
            "fuel_mwh_step": (p / self.eta) if self.eta > 0 else 0.0,
            "co2_kg_per_mw_step": p * self.co2_kg_per_mwh,
        }


# ---------------------------------------------------------------------------
# Konkrete Klassen mit realistischen Default-Parametern
# Quellen-Hinweis fuer die Seminararbeit:
#   - Wirkungsgrade: Fraunhofer ISE / VDE / IEA
#   - CO2-Emissionsfaktoren: Umweltbundesamt 2023 (kg CO2 / MWh_el)
#   - Rampenraten: technische Datenblaetter / Studien zur Regelfaehigkeit
# ---------------------------------------------------------------------------

@dataclass
class GasGuDPlant(DispatchableGenerator):
    """Gas- und Dampfturbinen-Kraftwerk (GuD).

    Schnelle Lastfolge, hoher Wirkungsgrad, mittlere CO2-Intensitaet.
    """
    p_min_mw: float = 50.0
    p_max_mw: float = 400.0
    ramp_mw_per_min: float = 10.0     # ca. 2.5 % P_rated/min
    eta: float = 0.58
    co2_kg_per_mwh: float = 350.0
    fuel: str = "natural_gas"


@dataclass
class CoalPlant(DispatchableGenerator):
    """Steinkohlekraftwerk.

    Traege, mittlerer Wirkungsgrad, hohe CO2-Intensitaet.
    """
    p_min_mw: float = 200.0
    p_max_mw: float = 700.0
    ramp_mw_per_min: float = 3.0
    eta: float = 0.42
    co2_kg_per_mwh: float = 900.0
    fuel: str = "hard_coal"


@dataclass
class BiomassPlant(DispatchableGenerator):
    """Biomasse-Heizkraftwerk.

    Dispatchierbar erneuerbar, mittlerer Wirkungsgrad. CO2-Bilanz wird in
    der Seminararbeit ueblicherweise als bilanziell neutral angesetzt
    (nachwachsend), Restemissionen aus Logistik werden hier vereinfacht
    auf 25 kg/MWh gesetzt.
    """
    p_min_mw: float = 5.0
    p_max_mw: float = 50.0
    ramp_mw_per_min: float = 1.0
    eta: float = 0.35
    co2_kg_per_mwh: float = 25.0
    fuel: str = "biomass"
