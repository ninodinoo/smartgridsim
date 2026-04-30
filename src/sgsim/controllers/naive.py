"""Naiver Controller — bewusst dumme Baseline.

Modelliert ein Stromnetz ohne intelligente Steuerung. In einem
100%-erneuerbaren System ohne fossile Kraftwerke laufen die dispatchierbaren
Erneuerbaren (Biomasse, Geothermie) auf hoher Festlast und die H2-Gasturbine
als statisches Backup auf einem festen Anteil. Speicher bleiben passiv.

Diese Strategie ist bewusst suboptimal — sie ueberproduziert oft, leert den
H2-Speicher unnoetig und nutzt die Kurzzeitspeicher gar nicht. Der
Vergleichspunkt fuer eine smarte Steuerung.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..components import (
    BiomassPlant,
    DispatchableGenerator,
    GeothermalPlant,
    HydrogenGasTurbine,
    Storage,
    TickContext,
)
from ..engine import Grid
from .base import Controller


@dataclass
class NaiveController(Controller):
    """Setzt einmalig konstante Sollwerte und ruehrt nichts mehr an.

    Default-Auslegung in einem 100%-erneuerbaren Mix:
        Biomasse 100 % (cheap renewable, immer voll)
        Geothermie 100 % (Grundlast)
        H2-Gasturbine 50 % (mittlere Festlast als Backup)
    """

    name: str = "naive"
    biomass_fraction: float = 1.00
    geothermal_fraction: float = 1.00
    h2_turbine_fraction: float = 0.50

    def initialize(self, grid: Grid) -> None:
        for c in grid.components:
            if isinstance(c, BiomassPlant):
                c.setpoint_mw = c.p_max_mw * self.biomass_fraction
            elif isinstance(c, GeothermalPlant):
                c.setpoint_mw = c.p_max_mw * self.geothermal_fraction
            elif isinstance(c, HydrogenGasTurbine):
                c.setpoint_mw = c.p_max_mw * self.h2_turbine_fraction
            elif isinstance(c, Storage):
                c.setpoint_mw = 0.0
            elif isinstance(c, DispatchableGenerator):
                # Falls noch fossile Restkomponenten in einem Szenario auftauchen
                c.setpoint_mw = c.p_max_mw * 0.5

    def step(self, grid: Grid, next_ctx: TickContext) -> None:
        # Bewusst leer: der naive Controller passt sich nicht an.
        return
