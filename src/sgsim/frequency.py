"""Vereinfachtes Frequenzmodell ueber die Swing-Equation.

Das Stromnetz ist nur stabil, wenn Erzeugung und Last in jedem Moment
ausgeglichen sind. Kurzfristige Bilanzabweichungen veraendern die
Netzfrequenz f, weil die kinetische Energie der rotierenden Schwung-
massen den Puffer bildet.

Modell (single-bus, vereinfacht):
    df/dt = (P_total) / (2 * H * S_base)        [pu/s]
    f_neu = f_alt + df/dt * dt
mit
    H        — aggregierte Tragheit [s]   (typisch 4–6 s in DE)
    S_base   — Bezugsleistung des Systems [MW]
    P_total  — algebraische Bilanz im Tick [MW]

Anschliessend wird f auf [49.0, 51.0] Hz gecappt und Abweichungen ueber
50 +/- 0.2 Hz als Frequenz-Brownout gezaehlt (UCTE Operational Handbook
50 +/- 0.2 Hz ist normal, ausserhalb wird Schutzabwurf ausgeloest).

Vereinfachung:
- Keine Frequenzregelung ueber Primaer-/Sekundaerregelreserve.
- Kein gleitendes Mittel ueber Tickgrenzen — die Frequenz ist konstant
  innerhalb eines 15-min-Tick-Intervalls (real schwankt sie schneller).
- Echte Inertia sinkt mit Erneuerbaren-Anteil (Umrichter-basiert),
  hier konstant gesetzt.
"""

from __future__ import annotations

from dataclasses import dataclass


F_NOMINAL_HZ = 50.0
F_DEAD_BAND_HZ = 0.2          # +/- 0.2 Hz = Normalbetrieb
F_TRIP_HZ = 0.5               # +/- 0.5 Hz = Schutzabwurf in Realitaet


@dataclass
class FrequencyState:
    """Zustand des Frequenzmodells."""

    inertia_h_s: float = 5.0          # Aggregierte Inertia [s]
    s_base_mw: float = 500.0          # Bezugsleistung [MW]
    f_hz: float = F_NOMINAL_HZ        # aktuelle Frequenz [Hz]

    droop: float = 0.05               # 5 % statisch (UCTE/ENTSO-E Standard)

    def step(self, p_total_mw: float, dt_s: float) -> float:
        """Frequenz nach einem Tick aktualisieren und zurueckgeben.

        Quasi-statische Naeherung: in einem 15-min-Tick (900 s) hat die
        Primaerregelung laengst einen Steady-State erreicht. Die statische
        Frequenzabweichung unter Droop-Regelung ist:

            df_steady = +P_imbalance * droop * F_NOMINAL / S_base

        Vorzeichenkonvention: Surplus (P_total > 0) hebt die Frequenz,
        Defizit (P_total < 0) senkt sie.

        Beispiel: 100 MW Defizit (P_total = -100), droop 0.05, S_base 500 MW
            df = -100 * 0.05 * 50 / 500 = -0.5 Hz — gerade am Limit

        Akkumulation ueber Ticks (transiente Inertia-Beitraege) wird
        vernachlaessigt, weil die Primaerregelung sie auf der Sekunden-
        Zeitskala wegregelt — auf 15-min-Tick-Skala unsichtbar.
        """
        if self.s_base_mw <= 0:
            return self.f_hz
        # Vorzeichen: P_total > 0 (Surplus) hebt Frequenz, P_total < 0 senkt sie.
        df_steady = p_total_mw * self.droop * F_NOMINAL_HZ / self.s_base_mw
        # Hard cap: ausserhalb der Trip-Zone setzt der Schutzabwurf ein und
        # die Frequenz wird durch Lastabwurf wieder ins Band gefuehrt.
        df_steady = max(-1.0, min(1.0, df_steady))
        self.f_hz = F_NOMINAL_HZ + df_steady
        return self.f_hz

    def deviation_hz(self) -> float:
        return self.f_hz - F_NOMINAL_HZ

    def is_outside_dead_band(self) -> bool:
        return abs(self.deviation_hz()) > F_DEAD_BAND_HZ

    def is_trip_zone(self) -> bool:
        return abs(self.deviation_hz()) > F_TRIP_HZ
