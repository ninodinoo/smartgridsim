# Eigene Komponenten und Controller schreiben

Anleitung, wie man `sgsim` ohne Eingriff in den Engine-Kern erweitert.

## Eigene Komponente

### 1. Klasse anlegen

Im passenden Submodul (oder einer neuen Datei) unter
`src/sgsim/components/` eine Dataclass definieren, die von `Component`
erbt:

```python
# src/sgsim/components/example.py
from __future__ import annotations
from dataclasses import dataclass

from .base import Component, TickContext


@dataclass
class TidalPlant(Component):
    """Gezeitenkraftwerk — sehr vereinfachtes Modell."""
    p_max_mw: float = 25.0
    period_h: float = 12.42        # halbtägliche Tide

    def step(self, dt_h: float, ctx: TickContext) -> float:
        import math
        phase = 2 * math.pi * ctx.sim_time_h / self.period_h
        return abs(math.sin(phase)) * self.p_max_mw

    def snapshot(self) -> dict[str, float]:
        return {"period_h": self.period_h}
```

**Pflicht-Konventionen:**
- `step()` liefert genau eine Wirkleistung [MW] mit korrektem Vorzeichen
  (siehe [`../components.md`](../components.md)).
- `snapshot()` ist optional und liefert Zusatz-Kennzahlen für das
  Mess-Log (z. B. SoC, Curtailment).

### 2. In der Registry eintragen

`src/sgsim/components/__init__.py` ergänzen:

```python
from .example import TidalPlant

__all__ = [..., "TidalPlant"]

COMPONENT_REGISTRY: dict[str, type[Component]] = {
    ...,
    "TidalPlant": TidalPlant,
}
```

Damit ist die Komponente aus YAML-Szenarien deserialisierbar.

### 3. Bei erneuerbarer Erzeugung: in `RENEWABLE_TYPES` aufnehmen

`src/sgsim/engine.py`:

```python
from .components import TidalPlant
RENEWABLE_TYPES = (..., TidalPlant)
```

Sonst zählt die Erzeugung **nicht** zum Renewable-Share.

### 4. Im Szenario verwenden

```yaml
# src/sgsim/scenarios/example_with_tides.yaml
components:
  - type: TidalPlant
    name: gezeiten_kueste
    p_max_mw: 25.0
    period_h: 12.42
```

Aufruf: `sgsim init --scenario src/sgsim/scenarios/example_with_tides.yaml`.

### 5. Tests dazu

`tests/test_components.py` (oder eine neue Datei):

```python
def test_tidal_plant_oscillates():
    from sgsim.components import TidalPlant, TickContext
    t = TidalPlant(name="t", p_max_mw=25)
    ctx0 = TickContext(sim_time_h=0, hour_of_day=0,
                       irradiance_w_m2=0, wind_speed_m_s=0, temperature_c=10)
    ctx_max = TickContext(sim_time_h=12.42/4, hour_of_day=3,
                       irradiance_w_m2=0, wind_speed_m_s=0, temperature_c=10)
    assert t.step(0.25, ctx0) == 0.0
    assert t.step(0.25, ctx_max) == pytest.approx(25.0, rel=0.01)
```

`pytest` lokal laufen lassen, sicherstellen dass alle bestehenden
Tests grün bleiben.

## Eigener Controller

### 1. Klasse anlegen

Im neuen Modul unter `src/sgsim/controllers/`:

```python
# src/sgsim/controllers/aggressive_storage.py
from __future__ import annotations
from dataclasses import dataclass

from ..components import BatteryStorage, TickContext
from ..engine import Grid
from .base import Controller


@dataclass
class AggressiveStorageController(Controller):
    """Beispiel: lädt Batterie immer voll, entlädt sofort bei Defizit."""
    name: str = "aggressive_storage"

    def initialize(self, grid: Grid) -> None:
        for c in grid.components:
            if isinstance(c, BatteryStorage):
                c.setpoint_mw = -c.p_max_charge_mw   # voll laden

    def step(self, grid: Grid, next_ctx: TickContext) -> None:
        # Logik nach jedem Tick anpassen
        for c in grid.components:
            if isinstance(c, BatteryStorage):
                if c.soc_mwh > c.capacity_mwh * 0.9:
                    c.setpoint_mw = c.p_max_discharge_mw  # entladen
                else:
                    c.setpoint_mw = -c.p_max_charge_mw    # weiter laden
```

### 2. In der Registry eintragen

`src/sgsim/controllers/__init__.py`:

```python
from .aggressive_storage import AggressiveStorageController

CONTROLLER_REGISTRY: dict[str, type[Controller]] = {
    ...,
    "aggressive_storage": AggressiveStorageController,
}
```

### 3. Verwenden

```bash
sgsim experiment run --controller aggressive_storage \
                     --steps 96 --seed 42 --out test.csv
```

## Eigener KI-Controller (LLM-basiert)

Subklasse von `AILoopController` (in `src/sgsim/ai/controllers.py`):

```python
@dataclass
class MyAIController(AILoopController):
    name: str = "my_ai"

    def decide(self, state: dict) -> dict:
        # Hier z. B. eigene Heuristik, externe API, oder ein lokales Modell.
        # Rückgabe: {"actions": [{"component": "...", "setpoint_mw": ...}, ...]}
        return {"actions": [
            {"component": "h2_gasturbine", "setpoint_mw": 100.0},
        ]}
```

Registrierung wie bei den anderen Controllern (siehe oben).

## Property-Tests gegen die neue Komponente

Wenn die neue Komponente Energieflüsse berührt, mit `tests/test_phase5.py`
prüfen, dass die **Bilanz weiter über alle Seeds schließt**:

```bash
python3.12 -m pytest tests/test_phase5.py -v
```

Schlägt der Energiebilanz-Test fehl, ist meist die `step()`-Methode nicht
seiteneffektfrei (z. B. mutiert `ctx`, das ist verboten).

## Eigenes Szenario entwerfen

Eine YAML-Datei in `src/sgsim/scenarios/` (oder anderswo, dann mit
`--scenario` als Pfad übergeben):

```yaml
name: mein_szenario
seed: 100
dt_min: 15

weather:
  cloudiness: 0.3
  mean_wind_m_s: 8.0
  mean_temp_c: 12.0

components:
  - type: ResidentialLoad
    name: wohnen
    base_mw: 50
    peak_mw: 80
  # ... weitere Komponenten
```

Felder müssen auf die `__init__`-Argumente der jeweiligen Klasse passen
— die Engine ruft `cls(**payload)` mit den YAML-Werten auf.

Sonderfall `PumpedHydroStorage`: kann mit `head_m` + `upper_volume_m3`
statt `capacity_mwh` initialisiert werden — dann berechnet
`from_geometry()` die Kapazität aus der Geometrie ($E = \rho V g h$).

## Master-Brief aktualisieren, wenn die Modellbasis sich ändert

Wenn deine Erweiterung die Stellgrößen einer KI-Steuerung verändert
(neue Komponentennamen, neue Limits), die Datei
`src/sgsim/ai/master_prompt.md` ergänzen. Der `AnthropicAIController` und
`sgsim brief` lesen daraus, ohne Neukompilieren.
