"""KI-basierte Controller, die ueber die JSON-Schnittstelle arbeiten.

Architektur:
    AILoopController     abstrakte Basis (decide(state) -> action)
    RandomAIController   demonstriert die Schnittstelle, zufaellige Setpoints
    AnthropicAIController  Adapter fuer die Anthropic-API mit Prompt-Caching

Alle drei sind ganz normale Controller (siehe sgsim.controllers.base.Controller),
laufen also ueber denselben Experiment-Mechanismus wie naive und rule_based.
"""

from __future__ import annotations

import json
import os
import random
import re
from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..components import (
    BiomassPlant,
    DispatchableGenerator,
    PVPlant,
    Storage,
    TickContext,
    WindTurbine,
)
from ..controllers.base import Controller
from ..engine import Grid
from .action import apply_action
from .state import grid_snapshot


# ---------------------------------------------------------------------------
# Basis
# ---------------------------------------------------------------------------

@dataclass
class AILoopController(Controller):
    """Loop-Schicht: liest Snapshot, bittet decide() um eine Aktion, wendet sie an."""

    name: str = "ai_loop"
    warnings: list[str] = field(default_factory=list)

    def initialize(self, grid: Grid) -> None:
        # Sinnvolle Defaults, sodass die KI nicht ins Brownout-Loch laeuft, bevor
        # sie ihre erste Entscheidung treffen kann.
        for c in grid.components:
            if isinstance(c, BiomassPlant):
                c.setpoint_mw = c.p_max_mw
            elif isinstance(c, DispatchableGenerator):
                c.setpoint_mw = c.p_min_mw
            elif isinstance(c, Storage):
                c.setpoint_mw = 0.0
            elif isinstance(c, (PVPlant, WindTurbine)):
                c.curtailment = 0.0

    def step(self, grid: Grid, next_ctx: TickContext) -> None:
        snap = grid_snapshot(grid, next_ctx)
        action = self.decide(snap)
        new_warnings = apply_action(grid, action)
        if new_warnings:
            self.warnings.extend(
                f"step {grid.step_count}: {w}" for w in new_warnings
            )

    @abstractmethod
    def decide(self, state: dict[str, Any]) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# RandomAIController — sofort lauffaehig, fuer Schnittstellen-Tests
# ---------------------------------------------------------------------------

@dataclass
class RandomAIController(AILoopController):
    """Zufaellige (aber im Rahmen) Setpoints — als Demo der KI-Schnittstelle.

    Der wissenschaftliche Wert ist gering ("Affe-am-Klavier"-Baseline), aber:
    sie zeigt, dass blinde Steuerung dramatisch schlechter ist als selbst die
    naive Strategie — eine zusaetzliche Vergleichsdimension fuer die Arbeit.
    """

    name: str = "random_ai"
    seed: int = 0

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        actions: list[dict[str, Any]] = []
        for name, info in state["components"].items():
            t = info["type"]
            if t == "dispatchable_generator":
                lo, hi = info["p_min_mw"], info["p_max_mw"]
                # Zufaellig zwischen 0 und P_max (mit etwas Wahrscheinlichkeit aus)
                if self._rng.random() < 0.2:
                    sp = 0.0
                else:
                    sp = self._rng.uniform(lo, hi)
                actions.append({"component": name, "setpoint_mw": sp})
            elif t in ("battery", "pumped_hydro"):
                lo = -info["p_max_charge_mw"]
                hi = info["p_max_discharge_mw"]
                actions.append({"component": name,
                                "setpoint_mw": self._rng.uniform(lo, hi)})
            elif t in ("pv", "wind"):
                actions.append({"component": name,
                                "curtailment": self._rng.uniform(0.0, 0.3)})
        return {"actions": actions}


# ---------------------------------------------------------------------------
# AnthropicAIController — echte LLM-Steuerung
# ---------------------------------------------------------------------------

def _load_master_prompt() -> str:
    """Den kanonischen Master-Prompt aus master_prompt.md laden.

    Single Source of Truth: derselbe Text, den `sgsim brief` ausgibt, wird
    hier als System-Prompt verwendet. Aenderungen am Brief wirken sich
    automatisch auch auf die API-Steuerung aus.
    """
    from pathlib import Path
    path = Path(__file__).parent / "master_prompt.md"
    return path.read_text(encoding="utf-8")


# Anthropic-spezifische Ergaenzung: das LLM antwortet hier ueber die
# Messages-API, nicht ueber die CLI. Es bekommt deshalb zusaetzlich ein
# straffes Antwort-Schema vorgeschrieben.
_ANTHROPIC_RESPONSE_INSTRUCTION = """

---

## Antwortformat (NUR fuer den API-Controller)

Du antwortest hier nicht ueber die CLI, sondern direkt mit einem JSON-Objekt
der folgenden Form (keine Markdown-Codeblocks, keine Prosa drumherum):

{"actions": [
  {"component": "<name>", "setpoint_mw": <float>},
  {"component": "<name>", "curtailment": <0..1>}
]}

Du bekommst pro Aufruf den aktuellen Snapshot des Grids als JSON. Antworte
ausschliesslich mit dem Aktions-JSON-Objekt — sonst nichts."""


@dataclass
class AnthropicAIController(AILoopController):
    """Adapter, der die Anthropic-API als Decider verwendet.

    Aktiviert sich nur, wenn das `anthropic`-Paket installiert ist und ein
    API-Key vorliegt (env: ANTHROPIC_API_KEY oder als Argument).
    """

    name: str = "anthropic_ai"
    model: str = "claude-haiku-4-5-20251001"
    api_key: str | None = None
    max_tokens: int = 1024

    def __post_init__(self) -> None:
        try:
            import anthropic                                 # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "Das Paket 'anthropic' ist nicht installiert. "
                "Bitte 'pip install anthropic' ausfuehren."
            ) from e
        key = self.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "Kein Anthropic-API-Key gefunden. ANTHROPIC_API_KEY setzen oder "
                "AnthropicAIController(api_key=...) explizit uebergeben."
            )
        self._client = anthropic.Anthropic(api_key=key)
        self._system_prompt = _load_master_prompt() + _ANTHROPIC_RESPONSE_INSTRUCTION

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        message = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            # System-Prompt mit Cache markiert: er ist pro Tick identisch und
            # wird nach dem ersten Aufruf aus dem Anthropic-Cache geladen
            # (TTL 5 min). Spart Token-Kosten in einer Loop.
            system=[
                {
                    "type": "text",
                    "text": self._system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {"role": "user", "content": json.dumps(state)},
            ],
        )
        text_blocks = [b.text for b in message.content if hasattr(b, "text")]
        text = "\n".join(text_blocks).strip()
        return _parse_action_json(text)


def _parse_action_json(text: str) -> dict[str, Any]:
    """Extrahiert das JSON-Objekt aus der Modellantwort.

    Defensive: akzeptiert auch geringfuegig dekorierte Antworten (z. B. in
    ```json ... ``` Bloecken) und falscher Whitespace.
    """
    # Markdown-Codeblock entfernen
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    # Erstes balanciertes Objekt finden
    start = text.find("{")
    if start == -1:
        return {"actions": []}
    depth = 0
    end = -1
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        return {"actions": []}
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {"actions": []}
