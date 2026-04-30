"""Lasten (Verbraucher).

Lasten liefern negative Wirkleistung. Tagesgang ist als Sinus-/Glockenkurven-
Approximation an typische BDEW-Standardlastprofile umgesetzt; spaeter durch
echte Stundenwerte ersetzbar (data/bdew_h0.csv).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .base import Component, TickContext


@dataclass
class ResidentialLoad(Component):
    """Wohnlast — Annaeherung an BDEW H0 (Morgen- und Abendspitze)."""

    base_mw: float                    # Grundlast (Nacht)
    peak_mw: float                    # zusaetzliche Tagesspitze

    def step(self, dt_h: float, ctx: TickContext) -> float:
        h = ctx.hour_of_day
        morning = math.exp(-((h - 7.0) ** 2) / 6.0)
        evening = math.exp(-((h - 19.0) ** 2) / 8.0)
        shape = max(morning, evening)
        return -(self.base_mw + self.peak_mw * shape)


@dataclass
class CommercialLoad(Component):
    """Gewerbelast — Annaeherung an BDEW G0 (geschlossener Tagesblock 8–18)."""

    base_mw: float
    peak_mw: float

    def step(self, dt_h: float, ctx: TickContext) -> float:
        h = ctx.hour_of_day
        # Plateau 8..18, Flanken 6..8 und 18..20
        if 8.0 <= h <= 18.0:
            shape = 1.0
        elif 6.0 <= h < 8.0:
            shape = (h - 6.0) / 2.0
        elif 18.0 < h <= 20.0:
            shape = (20.0 - h) / 2.0
        else:
            shape = 0.0
        return -(self.base_mw + self.peak_mw * shape)


@dataclass
class IndustrialLoad(Component):
    """Industrielast — Annaeherung an BDEW L0 (rund um die Uhr fast konstant)."""

    base_mw: float
    night_reduction: float = 0.15     # 15 % weniger nachts (1-Schicht-Anteil)

    def step(self, dt_h: float, ctx: TickContext) -> float:
        h = ctx.hour_of_day
        if 22.0 <= h or h < 6.0:
            shape = 1.0 - self.night_reduction
        else:
            shape = 1.0
        return -self.base_mw * shape
