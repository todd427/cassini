"""Domain-specific assessment policies registered with EIP."""

from core.policy import PolicyRegistry
from policies.flood_road import FloodRoadPolicy
from policies.galileo_osnma import GalileoOsnmaPolicy


def build_default_registry() -> PolicyRegistry:
    """Build the default PolicyRegistry with built-in production/demo policies."""
    registry = PolicyRegistry()
    registry.register(FloodRoadPolicy())
    registry.register(GalileoOsnmaPolicy())
    return registry


__all__ = ["FloodRoadPolicy", "GalileoOsnmaPolicy", "build_default_registry"]
