"""Regelbasierter Smart-Grid-Controller (Merit-Order + Speicher-Heuristik).

Diese Strategie ist die starke Baseline gegen die KI antritt: sie nutzt
explizit Wissen ueber Kosten/Emissionen, hat eine Wettervorhersage fuer
den naechsten Zeitschritt (perfect foresight, eine bewusste Vereinfachung)
und entscheidet pro Tick rational.

Algorithmus pro Tick:
    1. Forecast: erwartete Last und erwartete Erneuerbaren-Einspeisung
       fuer den naechsten Tick (PV/Wind/Laufwasser sind zustandslos, ihr
       step() laesst sich gefahrlos im Voraus aufrufen).
    2. Biomasse laeuft als billige, dispatchierbare Erneuerbare immer voll.
    3. Residuallast = Last - Erneuerbar - Biomasse.
       Defizit (residual > 0):
           a. Speicher entladen (Pumpspeicher zuerst — groessere Reserve,
              hoeherer Wirkungsgrad bei Volllast als Batterie).
           b. Gas-GuD hochfahren (sauberer, schneller).
           c. Kohle als letzte Reserve.
       Ueberschuss (residual <= 0):
           a. Kohle/Gas auf 0 (CO2 sparen).
           b. Speicher laden (Batterie zuerst — schnellere Reaktion).
           c. PV/Wind abregeln, falls weiterhin Ueberschuss.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..components import (
    BatteryStorage,
    BiomassPlant,
    CoalPlant,
    Component,
    DispatchableGenerator,
    GasGuDPlant,
    PVPlant,
    PumpedHydroStorage,
    RunOfRiverHydro,
    Storage,
    TickContext,
    WindTurbine,
)
from ..engine import Grid
from .base import Controller


# Lasten erkennen wir am negativen step()-Output ueber alle nicht-Storage,
# nicht-Generator-Komponenten. Robuster: an konkreten Lastklassen.
from ..components.loads import (
    CommercialLoad,
    IndustrialLoad,
    ResidentialLoad,
)


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
    ) -> tuple[float, float, float]:
        """Liefert (load_mw, renewable_mw, hydro_mw) fuer den naechsten Tick.

        Aufruf von step() auf zustandslosen Komponenten ist gefahrlos (idempotent).
        """
        load_mw = 0.0
        renewable_mw = 0.0
        hydro_mw = 0.0
        for c in grid.components:
            if isinstance(c, _LOAD_TYPES):
                load_mw += -c.step(grid.dt_h, ctx)        # +-Vorzeichenwechsel
            elif isinstance(c, RunOfRiverHydro):
                hydro_mw += c.step(grid.dt_h, ctx)
            elif isinstance(c, (PVPlant, WindTurbine)):
                # Vorhersage ohne Curtailment, damit wir das Potenzial sehen
                old = c.curtailment
                c.curtailment = 0.0
                renewable_mw += c.step(grid.dt_h, ctx)
                c.curtailment = old
        return load_mw, renewable_mw + hydro_mw, hydro_mw

    # -- Auswahl-Hilfen ----------------------------------------------------

    @staticmethod
    def _filter(grid: Grid, cls: type[Component]) -> list[Component]:
        return [c for c in grid.components if isinstance(c, cls)]

    # -- Hauptlogik --------------------------------------------------------

    def step(self, grid: Grid, next_ctx: TickContext) -> None:
        load_mw, renewable_mw, _ = self._forecast(grid, next_ctx)

        # 1. Biomasse immer voll an (billige dispatchierbare Erneuerbare)
        biomass_p = 0.0
        for b in self._filter(grid, BiomassPlant):
            assert isinstance(b, BiomassPlant)
            b.setpoint_mw = b.p_max_mw
            biomass_p += b.p_max_mw

        # 2. Kohle "warm hold" auf P_min: traege Anlage, die nicht im 15-min-Takt
        #    abgeschaltet werden kann. Modelliert Realbetrieb (Kosten/Anfahrzeit).
        coal_must_run = 0.0
        for c in self._filter(grid, CoalPlant):
            assert isinstance(c, CoalPlant)
            c.setpoint_mw = c.p_min_mw
            coal_must_run += c.p_min_mw

        # 3. Defaults fuer Gas, Speicher, Curtailment
        for g in self._filter(grid, GasGuDPlant):
            assert isinstance(g, GasGuDPlant)
            g.setpoint_mw = 0.0
        for s in self._filter(grid, Storage):
            assert isinstance(s, Storage)
            s.setpoint_mw = 0.0
        for r in self._filter(grid, (PVPlant, WindTurbine)):
            r.curtailment = 0.0

        residual = load_mw - renewable_mw - biomass_p - coal_must_run

        if residual > 0.0:
            self._cover_deficit(grid, residual)
        elif residual < 0.0:
            self._absorb_surplus(grid, -residual, next_ctx)

    # -- Defizit decken ----------------------------------------------------

    def _cover_deficit(self, grid: Grid, deficit_mw: float) -> None:
        # 1. Speicher entladen — Pumpspeicher zuerst (typ. groessere E-Reserve)
        for cls in (PumpedHydroStorage, BatteryStorage):
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

        # 2. Gas-GuD hochfahren (sauberer als Kohle, schneller rampbar)
        for g in self._filter(grid, GasGuDPlant):
            if deficit_mw <= 0:
                return
            use = min(g.p_max_mw, deficit_mw)
            if 0 < use < g.p_min_mw:
                use = g.p_min_mw
            g.setpoint_mw = use
            deficit_mw -= use

        # 3. Kohle ueber P_min hinaus hochfahren (P_min wurde bereits in step() gesetzt)
        for c in self._filter(grid, CoalPlant):
            if deficit_mw <= 0:
                return
            extra_capacity = c.p_max_mw - c.p_min_mw
            extra = min(extra_capacity, deficit_mw)
            c.setpoint_mw = c.p_min_mw + extra
            deficit_mw -= extra

        # Restliches Defizit kann nicht gedeckt werden -> Brownout (in Metriken sichtbar)

    # -- Ueberschuss absorbieren ------------------------------------------

    def _absorb_surplus(
        self, grid: Grid, surplus_mw: float, next_ctx: TickContext
    ) -> None:
        # 1. Speicher laden — Batterie zuerst (schnell), dann Pumpspeicher
        for cls in (BatteryStorage, PumpedHydroStorage):
            for s in self._filter(grid, cls):
                if surplus_mw <= 0:
                    return
                free = max(0.0, (s.capacity_mwh - s.soc_mwh) / max(s.eta_charge, 1e-9) / grid.dt_h)
                use = min(s.p_max_charge_mw, free, surplus_mw)
                s.setpoint_mw = -use
                surplus_mw -= use

        # 2. Restueberschuss durch Curtailment (Wind zuerst, ist im Mittelfeld
        #    teurer als PV-Volllaststunden zu verlieren? — Konvention: PV zuerst,
        #    weil PV in Deutschland tendenziell ueberinstalliert).
        if surplus_mw <= 0:
            return
        for cls in (PVPlant, WindTurbine):
            for r in self._filter(grid, cls):
                if surplus_mw <= 0:
                    return
                # Volle (ungedrosselte) Leistung im naechsten Tick:
                old = r.curtailment
                r.curtailment = 0.0
                full = r.step(grid.dt_h, next_ctx)
                r.curtailment = old
                if full <= 1e-9:
                    continue
                cut = min(1.0, surplus_mw / full)
                r.curtailment = cut
                surplus_mw -= full * cut
