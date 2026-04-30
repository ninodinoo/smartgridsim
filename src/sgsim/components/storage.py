"""Energiespeicher.

Vorzeichenkonvention der Wirkleistung am Netzknoten:
    setpoint_mw > 0   Speicher entlaedt ins Netz
    setpoint_mw < 0   Speicher laedt aus dem Netz
    setpoint_mw = 0   Bereitschaft

Energiebuchhaltung mit Wirkungsgraden:
    Laden    (P < 0): in den Speicher gelangen |P| * eta_charge * dt MWh.
    Entladen (P > 0): aus dem Speicher entnommen werden P / eta_discharge * dt MWh.

Round-Trip-Wirkungsgrad: eta_rt = eta_charge * eta_discharge.

Begrenzungen:
    - Leistung: |P| <= p_max_charge_mw bzw. p_max_discharge_mw
    - Energie: min_soc_mwh <= soc_mwh <= capacity_mwh
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .base import Component, TickContext


@dataclass
class Storage(Component):
    """Generischer Speicher (Basisklasse, nicht direkt instanziieren)."""

    capacity_mwh: float
    soc_mwh: float                    # aktueller Energieinhalt
    p_max_charge_mw: float
    p_max_discharge_mw: float
    eta_charge: float                 # 0..1
    eta_discharge: float              # 0..1
    min_soc_mwh: float = 0.0
    setpoint_mw: float = 0.0

    def step(self, dt_h: float, ctx: TickContext) -> float:
        sp = self.setpoint_mw
        if sp > 0.0:
            # Entladen — limitiert durch P_max und durch verfuegbaren Vorrat
            p_max_by_energy = max(0.0,
                (self.soc_mwh - self.min_soc_mwh) * self.eta_discharge / dt_h)
            p = min(sp, self.p_max_discharge_mw, p_max_by_energy)
            self.soc_mwh -= p / self.eta_discharge * dt_h if self.eta_discharge > 0 else 0.0
            return p
        if sp < 0.0:
            # Laden — limitiert durch P_max und durch freien Restplatz
            free = max(0.0, (self.capacity_mwh - self.soc_mwh) / max(self.eta_charge, 1e-9) / dt_h)
            p_charge = min(-sp, self.p_max_charge_mw, free)
            self.soc_mwh += p_charge * self.eta_charge * dt_h
            return -p_charge
        return 0.0

    def snapshot(self) -> dict[str, float]:
        return {
            "setpoint_mw": self.setpoint_mw,
            "soc_mwh": self.soc_mwh,
            "soc_fraction": (
                (self.soc_mwh - self.min_soc_mwh)
                / max(self.capacity_mwh - self.min_soc_mwh, 1e-9)
            ),
        }


@dataclass
class BatteryStorage(Storage):
    """Lithium-Ionen-Batteriegrossspeicher (z. B. Quartiersbatterie).

    Realistische Eckdaten: η_rt ≈ 0.90, C-Rate 0.5–1, Mindest-SoC 10 %
    fuer Lebensdauerschonung.
    """

    eta_charge: float = 0.95
    eta_discharge: float = 0.95
    c_rate: float = 0.5               # Lade-/Entladestrom relativ zu Kapazitaet


@dataclass
class PumpedHydroStorage(Storage):
    """Pumpspeicherkraftwerk.

    Speichermedium: Wasser im Oberbecken. Energieinhalt:
        E [J] = rho * V * g * h         mit rho_water = 1000 kg/m^3, g = 9.81

    Damit ist `capacity_mwh` aus Volumen V und Fallhoehe h ableitbar (siehe
    Klassmethode `from_geometry`). Wirkungsgrade aus Datenblaettern:
    Pumpe ~0.88, Turbine ~0.91 → η_rt ≈ 0.80.
    """

    eta_charge: float = 0.88
    eta_discharge: float = 0.91
    head_m: float = 300.0             # Fallhoehe (informativ, fuer Doku)
    upper_volume_m3: float = 0.0      # Oberbeckenvolumen (informativ)

    @classmethod
    def from_geometry(
        cls,
        name: str,
        head_m: float,
        upper_volume_m3: float,
        p_max_charge_mw: float,
        p_max_discharge_mw: float,
        initial_fill: float = 0.5,
        **kwargs: float,
    ) -> "PumpedHydroStorage":
        """Konstruktor aus geometrischen/physikalischen Parametern.

        Berechnung der speicherbaren elektrischen Energie:
            E_pot [J]  = rho * V * g * h
            E [MWh]    = E_pot / 3.6e9
        Dies ist die *potentielle* Energie im Wasser; was bei Entladung
        elektrisch ans Netz geliefert wird, ist E * eta_discharge.
        """
        rho_water = 1000.0
        g = 9.81
        e_pot_j = rho_water * upper_volume_m3 * g * head_m
        capacity_mwh = e_pot_j / 3.6e9
        return cls(
            name=name,
            capacity_mwh=capacity_mwh,
            soc_mwh=capacity_mwh * initial_fill,
            p_max_charge_mw=p_max_charge_mw,
            p_max_discharge_mw=p_max_discharge_mw,
            head_m=head_m,
            upper_volume_m3=upper_volume_m3,
            **kwargs,
        )


@dataclass
class HydrogenStorage(Storage):
    """Wasserstoffspeicher (Power-to-Gas-to-Power).

    Sehr lange Speicherdauer, dafuer niedriger Round-Trip-Wirkungsgrad
    (Elektrolyse + Rueckverstromung in GuD oder Brennstoffzelle).
    """

    eta_charge: float = 0.65          # Elektrolyseur
    eta_discharge: float = 0.55       # Brennstoffzelle / H2-GuD
