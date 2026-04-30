"""Komponentenpaket — exportiert die Komponenten-API + Deserialisierungs-Registry.

Neue Komponenten werden hier registriert. Damit reicht ein einzelner Eintrag,
um sie aus YAML-/JSON-Szenarien laden zu koennen.
"""

from __future__ import annotations

from typing import Any

from .base import Component, TickContext
from .loads import CommercialLoad, IndustrialLoad, ResidentialLoad
from .renewables import PVPlant, RunOfRiverHydro, WindTurbine
from .dispatchable import (
    BiomassPlant,
    CoalPlant,
    DispatchableGenerator,
    GasGuDPlant,
)
from .storage import (
    BatteryStorage,
    HydrogenStorage,
    PumpedHydroStorage,
    Storage,
)

__all__ = [
    "Component",
    "TickContext",
    "ResidentialLoad",
    "CommercialLoad",
    "IndustrialLoad",
    "PVPlant",
    "WindTurbine",
    "RunOfRiverHydro",
    "DispatchableGenerator",
    "GasGuDPlant",
    "CoalPlant",
    "BiomassPlant",
    "Storage",
    "BatteryStorage",
    "PumpedHydroStorage",
    "HydrogenStorage",
    "COMPONENT_REGISTRY",
    "from_dict",
]


COMPONENT_REGISTRY: dict[str, type[Component]] = {
    "ResidentialLoad": ResidentialLoad,
    "CommercialLoad": CommercialLoad,
    "IndustrialLoad": IndustrialLoad,
    "PVPlant": PVPlant,
    "WindTurbine": WindTurbine,
    "RunOfRiverHydro": RunOfRiverHydro,
    "GasGuDPlant": GasGuDPlant,
    "CoalPlant": CoalPlant,
    "BiomassPlant": BiomassPlant,
    "BatteryStorage": BatteryStorage,
    "PumpedHydroStorage": PumpedHydroStorage,
    "HydrogenStorage": HydrogenStorage,
}


def from_dict(data: dict[str, Any]) -> Component:
    """Komponente aus serialisiertem Dict rekonstruieren.

    Sonderfall PumpedHydroStorage: wenn `capacity_mwh` nicht angegeben ist,
    aber `head_m` und `upper_volume_m3`, wird die Kapazitaet aus der
    Geometrie berechnet (E = rho * V * g * h).
    """
    payload = dict(data)
    type_name = payload.pop("type")
    cls = COMPONENT_REGISTRY[type_name]

    if cls is PumpedHydroStorage and "capacity_mwh" not in payload:
        head_m = payload.pop("head_m", 0.0)
        volume_m3 = payload.pop("upper_volume_m3", 0.0)
        p_max_charge = payload.pop("p_max_charge_mw")
        p_max_discharge = payload.pop("p_max_discharge_mw")
        initial_fill = payload.pop("initial_fill", 0.5)
        return PumpedHydroStorage.from_geometry(
            name=payload.pop("name"),
            head_m=head_m,
            upper_volume_m3=volume_m3,
            p_max_charge_mw=p_max_charge,
            p_max_discharge_mw=p_max_discharge,
            initial_fill=initial_fill,
            **payload,
        )

    return cls(**payload)
