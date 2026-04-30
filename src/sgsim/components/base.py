"""Komponenten-Basisklasse + Tick-Kontext.

Vorzeichenkonvention (Wirkleistung [MW] aus Sicht des Sammelknotens):
    Generator             P > 0   speist ein
    Load                  P < 0   entnimmt
    Storage               P > 0   beim Entladen, P < 0 beim Laden
    Sektorkopplungslast   P < 0   (z. B. Elektrolyseur, Waermepumpe)

Energie [MWh] = Leistung [MW] * dt [h].

Eine Komponente kann optional zusaetzliche Innenzustaende (SoC, aktueller
Setpoint, Schaltzustand) ueber `snapshot()` fuer das Mess-Log freigeben.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class TickContext:
    """Umgebung, die jeder Komponente pro Tick zur Verfuegung steht."""

    sim_time_h: float          # simulierte Zeit seit Init in Stunden
    hour_of_day: float         # 0..24, fuer Tagesgang (Sonne, Last)
    irradiance_w_m2: float     # globale Horizontalstrahlung
    wind_speed_m_s: float      # Windgeschwindigkeit auf Nabenhoehe
    temperature_c: float       # Aussentemperatur


@dataclass
class Component(ABC):
    """Abstrakte Basis aller Netzteilnehmer."""

    name: str

    @abstractmethod
    def step(self, dt_h: float, ctx: TickContext) -> float:
        """Einen Zeitschritt simulieren und Wirkleistung [MW] zurueckgeben."""

    def snapshot(self) -> dict[str, float]:
        """Optionale Zusatzwerte fuer das Mess-Log (z. B. SoC, Setpoint).

        Default: keine Zusatzwerte. Konkrete Komponenten ueberschreiben.
        """
        return {}

    def to_dict(self) -> dict[str, Any]:
        return {"type": type(self).__name__, **self.__dict__}
