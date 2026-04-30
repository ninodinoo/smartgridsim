"""Naiver Controller — bewusst dumme Baseline.

Modelliert ein Stromnetz ohne intelligente Steuerung: die fossilen Kraftwerke
laufen auf einem festen Anteil ihrer Maximallast, Speicher bleiben passiv,
Erneuerbare werden nicht abgeregelt. Diese Strategie ueberproduziert oft
und/oder versorgt zu Spitzenzeiten unzureichend — genau das ist der
Vergleichspunkt fuer "smarte" Strategien.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..components import (
    BiomassPlant,
    CoalPlant,
    DispatchableGenerator,
    GasGuDPlant,
    Storage,
    TickContext,
)
from ..engine import Grid
from .base import Controller


@dataclass
class NaiveController(Controller):
    """Setzt einmalig konstante fossile Sollwerte und ruehrt nichts mehr an.

    Default-Auslegung (Anteile von P_max):
        Kohle 60 %  (Grundlast)
        Gas-GuD 40 %  (Mittellast)
        Biomasse 100 %  (cheap renewable, immer voll)
    """

    name: str = "naive"
    coal_fraction: float = 0.60
    gas_fraction: float = 0.40
    biomass_fraction: float = 1.00

    def initialize(self, grid: Grid) -> None:
        for c in grid.components:
            if isinstance(c, CoalPlant):
                c.setpoint_mw = c.p_max_mw * self.coal_fraction
            elif isinstance(c, GasGuDPlant):
                c.setpoint_mw = c.p_max_mw * self.gas_fraction
            elif isinstance(c, BiomassPlant):
                c.setpoint_mw = c.p_max_mw * self.biomass_fraction
            elif isinstance(c, Storage):
                c.setpoint_mw = 0.0
            elif isinstance(c, DispatchableGenerator):
                c.setpoint_mw = c.p_max_mw * 0.5

    def step(self, grid: Grid, next_ctx: TickContext) -> None:
        # Bewusst leer: der naive Controller passt sich nicht an.
        return
