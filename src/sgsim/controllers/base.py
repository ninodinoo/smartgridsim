"""Controller-Schnittstelle.

Ein Controller bekommt Zugriff auf das Grid und mutiert es zwischen den Ticks
(setzt Sollwerte, Curtailment etc.). Er gibt nichts zurueck — alle Wirkungen
sind Seiteneffekte auf den Komponenten.

Lebenszyklus:
    initialize(grid)        einmal vor dem ersten Tick
    step(grid, next_ctx)    vor jedem Tick (next_ctx = Wetter des kommenden Ticks)
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..components import TickContext
from ..engine import Grid


class Controller(ABC):
    """Abstrakte Basis aller Steuerungsstrategien."""

    name: str = "abstract"

    def initialize(self, grid: Grid) -> None:
        """Optionale einmalige Vorbereitung (Default: nichts)."""

    @abstractmethod
    def step(self, grid: Grid, next_ctx: TickContext) -> None:
        """Eingriffe vor dem naechsten Tick."""
