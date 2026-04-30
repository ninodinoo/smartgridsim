"""CSV-Loader fuer echte BDEW-Lastprofile und DWD-Wetterdaten.

Fuer die Seminararbeit kann der Nutzer eigene CSV-Dateien einbinden, ohne den
Komponenten-Code zu aendern. Format:

  BDEW-Lastprofil:
      hour_of_day,relative_load     (96 Zeilen fuer 15-min-Aufloesung)
      0.00,0.43
      0.25,0.42
      ...

  DWD-Wetter (eine Zeile pro Stunde oder feiner):
      hour_of_year,irradiance_w_m2,wind_m_s,temperature_c
      0,0,5.2,3.1
      ...

Sobald geladen, ueberschreibt die Funktion die `step()`-Methode der jeweiligen
Komponenten via Monkey-Patching ODER liefert eine Helferklasse, die als
Drop-in-Komponente verwendet werden kann.

Hier wird die Drop-in-Variante implementiert: `CsvProfileLoad` und
`CsvWeather`.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .components.base import Component, TickContext
from .weather import SyntheticWeather


# ---------------------------------------------------------------------------
# CSV-Last
# ---------------------------------------------------------------------------

@dataclass
class CsvProfileLoad(Component):
    """Last, deren Tagesgang aus einer CSV-Datei kommt.

    CSV-Format: zwei Spalten `hour_of_day,relative_load`. Beliebig viele
    Zeilen — wird linear interpoliert.

    Skalierung: `peak_mw` ist das absolute Maximum der Last. Die
    relative_load-Werte werden auf [0, 1] normiert.
    """

    csv_path: str = ""
    peak_mw: float = 100.0
    _hours: list[float] = field(default_factory=list, repr=False)
    _values: list[float] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if not self.csv_path:
            return
        with Path(self.csv_path).open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = sorted(reader, key=lambda r: float(r["hour_of_day"]))
        self._hours = [float(r["hour_of_day"]) for r in rows]
        raw = [float(r["relative_load"]) for r in rows]
        m = max(raw) if raw else 1.0
        self._values = [v / m for v in raw] if m > 0 else raw

    def _interp(self, h: float) -> float:
        if not self._hours:
            return 0.0
        # Modulo 24
        h = h % 24.0
        # Lineare Suche reicht fuer kleine Profile
        if h <= self._hours[0]:
            return self._values[0]
        if h >= self._hours[-1]:
            return self._values[-1]
        for i in range(1, len(self._hours)):
            if self._hours[i] >= h:
                h0, h1 = self._hours[i - 1], self._hours[i]
                v0, v1 = self._values[i - 1], self._values[i]
                w = (h - h0) / (h1 - h0) if h1 > h0 else 0.0
                return v0 + (v1 - v0) * w
        return self._values[-1]

    def step(self, dt_h: float, ctx: TickContext) -> float:
        return -(self._interp(ctx.hour_of_day) * self.peak_mw)


# ---------------------------------------------------------------------------
# CSV-Wetter
# ---------------------------------------------------------------------------

@dataclass
class CsvWeather(SyntheticWeather):
    """Wettermodell aus einer CSV-Datei.

    Erbt von SyntheticWeather, ueberschreibt aber die drei Methoden.
    Wenn keine CSV vorhanden ist, faellt die Klasse auf die synthetische
    Approximation zurueck (Vererbung).

    CSV-Format:
        hour_of_year,irradiance_w_m2,wind_m_s,temperature_c

    Beim Indexieren wird sim_time_h modulo der CSV-Laenge genommen, sodass
    laengere Simulationen das CSV "loopen" (z. B. eine Jahres-CSV als
    Repeat-Quelle fuer mehrere Jahre).
    """

    csv_path: str = ""
    _records: list[tuple[float, float, float, float]] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.csv_path:
            return
        with Path(self.csv_path).open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                self._records.append((
                    float(r["hour_of_year"]),
                    float(r["irradiance_w_m2"]),
                    float(r["wind_m_s"]),
                    float(r["temperature_c"]),
                ))
        self._records.sort(key=lambda x: x[0])

    def _csv_lookup(self, sim_time_h: float, idx: int) -> float | None:
        if not self._records:
            return None
        max_h = self._records[-1][0]
        # Loop in der CSV-Laenge
        h_in_csv = sim_time_h % (max_h + 1.0) if max_h > 0 else sim_time_h
        # Nearest neighbor
        nearest = min(self._records, key=lambda r: abs(r[0] - h_in_csv))
        return nearest[idx]

    def irradiance(self, sim_time_h: float) -> float:
        v = self._csv_lookup(sim_time_h, 1)
        return v if v is not None else super().irradiance(sim_time_h)

    def wind_speed(self, sim_time_h: float) -> float:
        v = self._csv_lookup(sim_time_h, 2)
        return v if v is not None else super().wind_speed(sim_time_h)

    def temperature(self, sim_time_h: float) -> float:
        v = self._csv_lookup(sim_time_h, 3)
        return v if v is not None else super().temperature(sim_time_h)
