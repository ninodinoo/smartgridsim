"""Regelbasierter Smart-Grid-Controller (Merit-Order + Speicher-Heuristik).

In einem 100%-erneuerbaren System ist die Merit-Order deutlich anders als
in einem fossilen Mix: alle Erzeuger sind im Wesentlichen "frei", also
priorisiert die Strategie nach **Knappheit** (H2 ist saisonal knapp,
PV/Wind volatil, Bio/Geothermie regelbar) und nach **Round-Trip-Wirkungs-
graden** der Speicher.

Algorithmus pro Tick:
    1. Forecast: erwartete Last und erwartete Erneuerbaren-Einspeisung.
    2. Biomasse + Geothermie immer voll (cheap renewable, dispatchable).
    3. Residuallast = Last - Erneuerbar - Bio - Geothermie.
       Defizit:
           a. Batterie entladen (schnellste Reaktion, hoeche eta_rt 0.90).
           b. Pumpspeicher entladen (eta_rt 0.80, mittel).
           c. H2-Speicher entladen (eta_rt 0.36, schlecht — letztes Mittel).
           d. H2-Gasturbine hochfahren als Reserve.
       Ueberschuss:
           a. Batterie laden (schnell, hoch eff.).
           b. Pumpspeicher laden.
           c. H2-Speicher laden via Elektrolyse (saisonale Reserve aufbauen).
           d. PV/Wind abregeln, falls weiterhin Ueberschuss.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..components import (
    BatteryStorage,
    BiomassPlant,
    Component,
    DispatchableGenerator,
    GeothermalPlant,
    HydrogenGasTurbine,
    HydrogenStorage,
    PVPlant,
    PumpedHydroStorage,
    RunOfRiverHydro,
    Storage,
    TickContext,
    WindTurbine,
)
from ..components.loads import (
    CommercialLoad,
    IndustrialLoad,
    ResidentialLoad,
)
from ..engine import Grid
from .base import Controller


_LOAD_TYPES = (ResidentialLoad, CommercialLoad, IndustrialLoad)
_NONDISPATCH_RENEWABLE_TYPES = (PVPlant, WindTurbine, RunOfRiverHydro)


@dataclass
class RuleBasedController(Controller):
    name: str = "rule_based"

    # -- Initialisierung ---------------------------------------------------

    def initialize(self, grid: Grid) -> None:
        for c in grid.components:
            if isinstance(c, DispatchableGenerator):
                c.setpoint_mw = 0.0
            elif isinstance(c, Storage):
                c.setpoint_mw = 0.0
            if isinstance(c, (PVPlant, WindTurbine)):
                c.curtailment = 0.0

    # -- Forecast-Helfer ---------------------------------------------------

    def _forecast(
        self, grid: Grid, ctx: TickContext
    ) -> tuple[float, float]:
        """Liefert (load_mw, renewable_mw) fuer den naechsten Tick.

        Aufruf von step() auf zustandslosen Komponenten ist gefahrlos
        (idempotent fuer Lasten, PV, Wind, Hydro).
        """
        load_mw = 0.0
        renewable_mw = 0.0
        for c in grid.components:
            if isinstance(c, _LOAD_TYPES):
                load_mw += -c.step(grid.dt_h, ctx)
            elif isinstance(c, RunOfRiverHydro):
                renewable_mw += c.step(grid.dt_h, ctx)
            elif isinstance(c, (PVPlant, WindTurbine)):
                old = c.curtailment
                c.curtailment = 0.0
                renewable_mw += c.step(grid.dt_h, ctx)
                c.curtailment = old
        return load_mw, renewable_mw

    @staticmethod
    def _filter(grid: Grid, cls):
        return [c for c in grid.components if isinstance(c, cls)]

    # -- Hauptlogik --------------------------------------------------------

    def step(self, grid: Grid, next_ctx: TickContext) -> None:
        load_mw, renewable_mw = self._forecast(grid, next_ctx)

        # 1. Biomasse + Geothermie immer voll (billige dispatchierbare Erneuerbare)
        cheap_dispatch_p = 0.0
        for cls in (BiomassPlant, GeothermalPlant):
            for g in self._filter(grid, cls):
                g.setpoint_mw = g.p_max_mw
                cheap_dispatch_p += g.p_max_mw

        # 2. Reset H2-Turbine, Speicher, Curtailment
        for h in self._filter(grid, HydrogenGasTurbine):
            h.setpoint_mw = 0.0
        for s in self._filter(grid, Storage):
            s.setpoint_mw = 0.0
        for r in self._filter(grid, (PVPlant, WindTurbine)):
            r.curtailment = 0.0

        residual = load_mw - renewable_mw - cheap_dispatch_p

        if residual > 0.0:
            self._cover_deficit(grid, residual)
        elif residual < 0.0:
            self._absorb_surplus(grid, -residual, next_ctx)

    # -- Defizit decken ----------------------------------------------------

    def _cover_deficit(self, grid: Grid, deficit_mw: float) -> None:
        # Reihenfolge: hoechster Round-Trip-Wirkungsgrad zuerst.
        # Batterie (~0.90) > Pumpspeicher (~0.80) > H2-Turbine > H2-Speicher (~0.36)

        for cls in (BatteryStorage, PumpedHydroStorage):
            for s in self._filter(grid, cls):
                if deficit_mw <= 0:
                    return
                avail = min(
                    s.p_max_discharge_mw,
                    max(0.0, (s.soc_mwh - s.min_soc_mwh) * s.eta_discharge / grid.dt_h),
                )
                use = min(avail, deficit_mw)
                s.setpoint_mw = use
                deficit_mw -= use

        # H2-Gasturbine als dispatchierbares Backup
        for h in self._filter(grid, HydrogenGasTurbine):
            if deficit_mw <= 0:
                return
            use = min(h.p_max_mw, deficit_mw)
            if 0 < use < h.p_min_mw:
                use = h.p_min_mw
            h.setpoint_mw = use
            deficit_mw -= use

        # Letztes Mittel: H2-Speicher direkt entladen (z. B. Brennstoffzelle).
        # Niedrigster Round-Trip-Wirkungsgrad — nur wenn alles andere nicht reicht.
        for s in self._filter(grid, HydrogenStorage):
            if deficit_mw <= 0:
                return
            avail = min(
                s.p_max_discharge_mw,
                max(0.0, (s.soc_mwh - s.min_soc_mwh) * s.eta_discharge / grid.dt_h),
            )
            use = min(avail, deficit_mw)
            s.setpoint_mw = use
            deficit_mw -= use

    # -- Ueberschuss absorbieren ------------------------------------------

    def _absorb_surplus(
        self, grid: Grid, surplus_mw: float, next_ctx: TickContext
    ) -> None:
        # Reihenfolge: Batterie (schnell) > Pumpspeicher (mittel) >
        # H2-Speicher (saisonale Reserve aufbauen)

        for cls in (BatteryStorage, PumpedHydroStorage, HydrogenStorage):
            for s in self._filter(grid, cls):
                if surplus_mw <= 0:
                    return
                free = max(0.0,
                    (s.capacity_mwh - s.soc_mwh) / max(s.eta_charge, 1e-9) / grid.dt_h)
                use = min(s.p_max_charge_mw, free, surplus_mw)
                s.setpoint_mw = -use
                surplus_mw -= use

        # Letzter Schritt: PV/Wind abregeln
        if surplus_mw <= 0:
            return
        for cls in (PVPlant, WindTurbine):
            for r in self._filter(grid, cls):
                if surplus_mw <= 0:
                    return
                old = r.curtailment
                r.curtailment = 0.0
                full = r.step(grid.dt_h, next_ctx)
                r.curtailment = old
                if full <= 1e-9:
                    continue
                cut = min(1.0, surplus_mw / full)
                r.curtailment = cut
                surplus_mw -= full * cut
