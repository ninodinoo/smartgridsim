"""Controller-Paket: Steuerungsstrategien fuer den Vergleich."""

from .base import Controller
from .naive import NaiveController
from .rule_based import RuleBasedController

__all__ = ["Controller", "NaiveController", "RuleBasedController",
           "CONTROLLER_REGISTRY"]

CONTROLLER_REGISTRY: dict[str, type[Controller]] = {
    "naive": NaiveController,
    "rule_based": RuleBasedController,
}
