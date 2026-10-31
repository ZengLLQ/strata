"""External service integration adapters and test environment harnesses."""

from strata.adapters.base import BaseServiceAdapter
from strata.adapters.docker import DockerEnvironmentManager
from strata.adapters.harness import IntegrationHarness, IntegrationNodeProxy
from strata.adapters.http import HttpServiceAdapter

__all__ = [
    "BaseServiceAdapter",
    "DockerEnvironmentManager",
    "HttpServiceAdapter",
    "IntegrationHarness",
    "IntegrationNodeProxy",
]
