"""Controller-Paket: Steuerungsstrategien fuer den Vergleich.

Die AI-Controller registrieren sich in sgsim.ai.__init__ in dieser Registry
nach (Auto-Registrierung beim Paketimport von sgsim.ai). Das CLI importiert
sgsim.ai mit Side-Effekt, damit die KI-Strategien in der --controller-Choice
auftauchen.
"""

from .base import Controller
from .naive import NaiveController
from .rule_based import RuleBasedController

__all__ = ["Controller", "NaiveController", "RuleBasedController",
           "CONTROLLER_REGISTRY"]

CONTROLLER_REGISTRY: dict[str, type[Controller]] = {
    "naive": NaiveController,
    "rule_based": RuleBasedController,
}
