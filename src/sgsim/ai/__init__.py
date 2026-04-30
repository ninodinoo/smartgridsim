"""KI-Schnittstelle: JSON-State, JSON-Action, KI-basierte Controller.

Side-Effekt beim Import: registriert die KI-Controller in
sgsim.controllers.CONTROLLER_REGISTRY, sodass sie als --controller-Wert
im Experiment-CLI verfuegbar sind.
"""

from .action import apply_action
from .controllers import (
    AILoopController,
    AnthropicAIController,
    RandomAIController,
)
from .state import grid_snapshot

__all__ = [
    "grid_snapshot",
    "apply_action",
    "AILoopController",
    "RandomAIController",
    "AnthropicAIController",
]


def _register() -> None:
    from ..controllers import CONTROLLER_REGISTRY
    CONTROLLER_REGISTRY["random_ai"] = RandomAIController
    CONTROLLER_REGISTRY["anthropic_ai"] = AnthropicAIController


_register()
