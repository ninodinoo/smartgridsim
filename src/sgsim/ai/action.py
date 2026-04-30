"""Aktion eines externen Deciders auf das Grid anwenden.

Action-Schema:
    {
      "actions": [
        {"component": <name>, "setpoint_mw": <float>}    # fuer Erzeuger/Speicher
        {"component": <name>, "curtailment": <0..1>}     # fuer PV/Wind
        ...
      ]
    }

Ungueltige Eintraege werden als Warnungen zurueckgegeben (kein Fehler, damit
ein Decider, der eine ungenaue Antwort liefert, das Experiment nicht
abbricht — das wuerde Brownouts produzieren, ist aber messbar).
"""

from __future__ import annotations

from typing import Any

from ..components import Component
from ..engine import Grid


def apply_action(grid: Grid, action: dict[str, Any]) -> list[str]:
    """Wendet eine Action-Liste an und liefert die Liste der Warnungen."""
    warnings: list[str] = []
    actions = action.get("actions", [])
    if not isinstance(actions, list):
        return [f"actions must be a list, got {type(actions).__name__}"]

    by_name: dict[str, Component] = {c.name: c for c in grid.components}

    for entry in actions:
        if not isinstance(entry, dict):
            warnings.append(f"action entry not a dict: {entry!r}")
            continue
        name = entry.get("component")
        if name is None or name not in by_name:
            warnings.append(f"unknown component: {name!r}")
            continue
        c = by_name[name]

        if "setpoint_mw" in entry:
            try:
                value = float(entry["setpoint_mw"])
            except (TypeError, ValueError):
                warnings.append(f"{name}: setpoint_mw not numeric: {entry['setpoint_mw']!r}")
                continue
            if not hasattr(c, "setpoint_mw"):
                warnings.append(f"{name}: not dispatchable (type {type(c).__name__})")
                continue
            setattr(c, "setpoint_mw", value)

        if "curtailment" in entry:
            try:
                value = float(entry["curtailment"])
            except (TypeError, ValueError):
                warnings.append(f"{name}: curtailment not numeric: {entry['curtailment']!r}")
                continue
            if not (0.0 <= value <= 1.0):
                warnings.append(f"{name}: curtailment out of range 0..1: {value}")
                value = max(0.0, min(1.0, value))
            if not hasattr(c, "curtailment"):
                warnings.append(f"{name}: not curtailable (type {type(c).__name__})")
                continue
            setattr(c, "curtailment", value)

    return warnings
