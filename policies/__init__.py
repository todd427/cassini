"""Domain-specific assessment policies registered with EIP."""

from core.policy import PolicyRegistry
from policies.flood_road import FloodRoadPolicy


def build_default_registry() -> PolicyRegistry:
    """Build the default PolicyRegistry with built-in production/demo policies."""
    registry = PolicyRegistry()
    registry.register(FloodRoadPolicy())
    return registry


__all__ = ["FloodRoadPolicy", "build_default_registry"]
