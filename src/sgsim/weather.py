"""Synthetisches Wettermodell.

Liefert reproduzierbare Strahlungs-, Wind- und Temperaturwerte als Funktion
der simulierten Zeit. In spaeteren Iterationen durch DWD-/PVGIS-Daten
ersetzbar (gleiche Schnittstelle).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class SyntheticWeather:
    """Tagesgang + leichte stochastische Variabilitaet."""

    seed: int = 42
    latitude_deg: float = 50.0          # ~ Mitteldeutschland
    cloudiness: float = 0.3             # 0 = klar, 1 = bedeckt
    mean_wind_m_s: float = 6.0
    mean_temp_c: float = 12.0

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def irradiance(self, sim_time_h: float) -> float:
        """Globale Horizontalstrahlung in W/m^2.

        Naeherung: Sinusboegen ueber den Tag, nachts 0. Spitzenwert bei
        klarem Himmel ca. 900 W/m^2, durch Bewoelkung gedaempft.
        """
        h = sim_time_h % 24.0
        if h < 6.0 or h > 20.0:
            return 0.0
        # Sinusbogen 6:00 .. 20:00 Uhr, Maximum 13:00
        phase = math.pi * (h - 6.0) / 14.0
        clear_sky = 900.0 * math.sin(phase)
        noise = self._rng.uniform(-0.05, 0.05)
        value = clear_sky * (1.0 - 0.8 * self.cloudiness) * (1.0 + noise)
        return max(0.0, value)

    def wind_speed(self, sim_time_h: float) -> float:
        """Windgeschwindigkeit auf Nabenhoehe [m/s]."""
        # leichte Tagesschwankung + Rauschen, untere Schranke 0
        diurnal = 1.0 + 0.2 * math.sin(2 * math.pi * sim_time_h / 24.0)
        noise = self._rng.uniform(-1.5, 1.5)
        return max(0.0, self.mean_wind_m_s * diurnal + noise)

    def temperature(self, sim_time_h: float) -> float:
        """Aussentemperatur [degC] mit Tagesgang (Min ~6:00, Max ~15:00)."""
        h = sim_time_h % 24.0
        diurnal = -math.cos(2 * math.pi * (h - 3.0) / 24.0)
        return self.mean_temp_c + 6.0 * diurnal
