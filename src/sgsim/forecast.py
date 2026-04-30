"""Forecast-Hilfen mit Rauschen — eliminiert die "perfect foresight"-Vereinfachung.

Der RuleBasedController hat bisher die Komponenten-Methoden mit dem ECHTEN
naechsten TickContext aufgerufen — er sah die Zukunft also exakt. Ein
realer Controller hat nur ein verrauschtes Forecast-Modell.

Diese Funktion liefert einen "verrauschten" TickContext: Wetterwerte werden
mit einem Gauss-Rauschen versehen, das mit der Vorhersage-Horizon waechst.
Fuer 15-min-Forecasts ist die Streuung typisch klein (5-10 %), bei mehreren
Stunden steigt sie deutlich.

Die Engine ruft das nicht selbst — der Controller darf entscheiden, ob er
den verrauschten oder den exakten Forecast nutzt.
"""

from __future__ import annotations

import random

from .components import TickContext


def noisy_forecast(
    ctx: TickContext,
    horizon_h: float = 0.25,
    rng: random.Random | None = None,
    irradiance_relative_sigma: float = 0.10,
    wind_relative_sigma: float = 0.15,
    temperature_absolute_sigma: float = 0.5,
) -> TickContext:
    """Liefert einen TickContext mit Wetter-Rauschen ueber dem Horizon.

    Default-Streuungen entsprechen einer naiven persistenz-basierten Prognose:
    ~10 % Strahlung, ~15 % Wind, ~0.5 K Temperatur fuer 15-min-Vorhersage.
    Die Streuungen skalieren mit sqrt(horizon) — 1-h-Forecast ist 2x verrauscht.
    """
    rng = rng or random.Random()
    scale = (horizon_h / 0.25) ** 0.5

    irr = ctx.irradiance_w_m2 * (1.0 + rng.gauss(0.0, irradiance_relative_sigma * scale))
    wind = ctx.wind_speed_m_s * (1.0 + rng.gauss(0.0, wind_relative_sigma * scale))
    temp = ctx.temperature_c + rng.gauss(0.0, temperature_absolute_sigma * scale)

    return TickContext(
        sim_time_h=ctx.sim_time_h,
        hour_of_day=ctx.hour_of_day,
        irradiance_w_m2=max(0.0, irr),
        wind_speed_m_s=max(0.0, wind),
        temperature_c=temp,
    )
