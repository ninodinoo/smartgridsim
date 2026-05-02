"""Vereinfachte Wirtschaftlichkeitsmetriken.

Berechnet aus einer Tick-Historie:
  - variable Erzeugungskosten (Brennstoff + variable O&M, EUR/MWh)
  - CO2-Zertifikate-Kosten (EU-ETS, EUR/t CO2)
  - Strommarkterloese (Day-Ahead-Mittelpreis × erzeugte MWh, EUR)
  - Speicher-Lebensdauerkosten (proportional zur Lade-/Entladeleistung,
    typisch Cents/kWh fuer Batterien)
  - Brownout-Schadenskosten (Value of Lost Load, ueblich 5-10 EUR/kWh in DE)

Standard-Annahmen werden in den `EconomicsParams` als Konstanten gesetzt;
Nutzer koennen sie ueberschreiben, wenn sie eigene Preise einsetzen.

Quellen-Hinweis fuer die Seminararbeit:
  - Brennstoffkosten: BNetzA Monitoring 2023
  - CO2-Zertifikate: EU-ETS, ~85 EUR/t (2023 Mittel)
  - Day-Ahead-Mittelpreis: SMARD 2023, ~95 EUR/MWh
  - Value of Lost Load: 5000-10000 EUR/MWh, BNetzA Versorgungssicherheits-
    Studie 2022
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .components import (
    BiomassPlant,
    CoalPlant,
    DispatchableGenerator,
    GasGuDPlant,
    GeothermalPlant,
    HydrogenGasTurbine,
    Storage,
)


@dataclass
class EconomicsParams:
    """Default-Preise (EUR). Alles ueberschreibbar fuer eigene Szenarien."""

    # Variable Brennstoffkosten je Erzeuger-Klasse [EUR/MWh_el]
    fuel_cost_eur_per_mwh: dict[str, float] = field(default_factory=lambda: {
        "GasGuDPlant": 80.0,
        "CoalPlant": 50.0,
        "BiomassPlant": 60.0,
        "GeothermalPlant": 5.0,
        "HydrogenGasTurbine": 120.0,   # H2 derzeit teuer
    })
    # CO2-Zertifikatspreis [EUR/t]
    co2_price_eur_per_t: float = 85.0
    # Strommarktpreis (Day-Ahead-Mittelwert) [EUR/MWh]
    market_price_eur_per_mwh: float = 95.0
    # Speicher-Lebensdauerkosten [EUR/MWh durchgesetzt]
    storage_throughput_cost_eur_per_mwh: float = 5.0
    # Value of Lost Load (Brownout-Schaden) [EUR/MWh]
    voll_eur_per_mwh: float = 7000.0


def compute_economics(grid, params: EconomicsParams | None = None) -> dict:
    """Berechnet Wirtschaftlichkeitsmetriken aus grid.history."""
    p = params or EconomicsParams()
    if not grid.history:
        return {}

    fuel_cost = 0.0
    co2_cost = 0.0
    market_revenue = 0.0
    storage_cost = 0.0

    components_by_name = {c.name: c for c in grid.components}

    for r in grid.history:
        # Brennstoff- und CO2-Kosten je dispatchierbarem Erzeuger
        for cname, p_mw in r.components.items():
            if p_mw <= 0:
                continue
            comp = components_by_name.get(cname)
            if isinstance(comp, DispatchableGenerator):
                cls_name = type(comp).__name__
                fuel_per = p.fuel_cost_eur_per_mwh.get(cls_name, 0.0)
                fuel_cost += p_mw * (r.sim_time_h - r.sim_time_h + grid.dt_h) * fuel_per

        # CO2-Zertifikate
        co2_cost += (r.co2_kg / 1000.0) * p.co2_price_eur_per_t

        # Erlös nur für tatsächlich bediente echte Last. Speicherentladung
        # oder Speicher-Laden darf nicht mehrfach als Markterlös zählen.
        deficit_mwh = max(0.0, -r.imbalance_mwh)
        served_load_mwh = max(0.0, r.load_energy_mwh - deficit_mwh)
        market_revenue += served_load_mwh * p.market_price_eur_per_mwh

        # Speicher-Throughput
        for cname, p_mw in r.components.items():
            comp = components_by_name.get(cname)
            if isinstance(comp, Storage):
                storage_cost += abs(p_mw) * grid.dt_h * p.storage_throughput_cost_eur_per_mwh

    total_co2_kg = sum(r.co2_kg for r in grid.history)
    unserved = sum(-r.imbalance_mwh for r in grid.history if r.imbalance_mwh < 0)
    voll_cost = unserved * p.voll_eur_per_mwh

    total_cost = fuel_cost + co2_cost + storage_cost + voll_cost
    net = market_revenue - total_cost

    return {
        "fuel_cost_eur": fuel_cost,
        "co2_cost_eur": co2_cost,
        "storage_cost_eur": storage_cost,
        "voll_cost_eur": voll_cost,
        "total_cost_eur": total_cost,
        "market_revenue_eur": market_revenue,
        "net_eur": net,
        "lcoe_eur_per_mwh": (
            total_cost / sum(r.energy_in_mwh for r in grid.history)
            if any(r.energy_in_mwh for r in grid.history) else 0.0
        ),
    }
