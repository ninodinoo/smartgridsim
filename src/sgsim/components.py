"""Komponenten des Smart-Grid-Modells.

Alle Leistungen sind in MW (positiv = Einspeisung ins Netz, negativ = Bezug).
Energien in MWh. Zeitschritt dt in Stunden.

Konvention der Vorzeichen aus Sicht des Sammelknotens:
    Generator      P > 0 (speist ein)
    Load           P < 0 (entnimmt)
    Storage        P > 0 beim Entladen, P < 0 beim Laden

Die Energiebilanz ueber einen Tick lautet damit:
    sum(P_i) * dt  -  P_loss * dt  =  0   (idealerweise)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Basisklasse
# ---------------------------------------------------------------------------

@dataclass
class Component(ABC):
    """Abstrakte Basis aller Netzteilnehmer."""

    name: str

    @abstractmethod
    def step(self, dt_h: float, ctx: "TickContext") -> float:
        """Einen Zeitschritt simulieren und Wirkleistung [MW] zurueckgeben.

        Vorzeichen siehe Modul-Docstring.
        """

    def to_dict(self) -> dict[str, Any]:
        return {"type": type(self).__name__, **self.__dict__}


@dataclass
class TickContext:
    """Umgebung, die jeder Komponente pro Tick zur Verfuegung steht."""

    sim_time_h: float          # simulierte Zeit seit Init in Stunden
    hour_of_day: float         # 0..24, fuer Tagesgang (Sonne, Last)
    irradiance_w_m2: float     # globale Horizontalstrahlung
    wind_speed_m_s: float      # Windgeschwindigkeit auf Nabenhoehe
    temperature_c: float       # Aussentemperatur


# ---------------------------------------------------------------------------
# Erzeuger
# ---------------------------------------------------------------------------

@dataclass
class PVPlant(Component):
    """Photovoltaik-Anlage.

    Modell:  P = G * A * eta_module * eta_inverter
    mit G  = Globalstrahlung [W/m^2], A = Modulflaeche [m^2].
    Skaliert auf MW: P[MW] = G * A * eta / 1e6.
    """

    area_m2: float                    # gesamte Modulflaeche
    eta_module: float = 0.20          # typische Si-Module 18-22 %
    eta_inverter: float = 0.97        # Wechselrichter-Wirkungsgrad
    curtailment: float = 0.0          # 0..1, vom Controller gesetzt

    def step(self, dt_h: float, ctx: TickContext) -> float:
        p_w = ctx.irradiance_w_m2 * self.area_m2 * self.eta_module * self.eta_inverter
        p_mw = p_w / 1e6
        return p_mw * (1.0 - self.curtailment)


# ---------------------------------------------------------------------------
# Lasten
# ---------------------------------------------------------------------------

@dataclass
class ResidentialLoad(Component):
    """Vereinfachte Wohngebiets-Last mit Tagesgang.

    Profil ist eine Sinus-Approximation an typische BDEW-H0-Charakteristik:
    Morgenspitze ~7 Uhr, Abendspitze ~19 Uhr. Spaeter durch echtes BDEW-H0
    ersetzbar (data/bdew_h0.csv).
    """

    base_mw: float                    # Grundlast (Nacht)
    peak_mw: float                    # zusaetzliche Tagesspitze

    def step(self, dt_h: float, ctx: TickContext) -> float:
        import math
        h = ctx.hour_of_day
        # zwei Glockenkurven um 7:00 und 19:00 Uhr
        morning = math.exp(-((h - 7.0) ** 2) / 6.0)
        evening = math.exp(-((h - 19.0) ** 2) / 8.0)
        shape = max(morning, evening)
        load = self.base_mw + self.peak_mw * shape
        return -load  # Vorzeichen: Bezug aus dem Netz


# ---------------------------------------------------------------------------
# Registry: Typname (str) -> Klasse, fuer Deserialisierung aus JSON/YAML
# ---------------------------------------------------------------------------

COMPONENT_REGISTRY: dict[str, type[Component]] = {
    "PVPlant": PVPlant,
    "ResidentialLoad": ResidentialLoad,
}


def from_dict(data: dict[str, Any]) -> Component:
    """Komponente aus serialisiertem Dict rekonstruieren."""
    payload = dict(data)
    type_name = payload.pop("type")
    cls = COMPONENT_REGISTRY[type_name]
    return cls(**payload)
