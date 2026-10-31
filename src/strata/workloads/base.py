"""Workload generation base classes and protocols."""

from __future__ import annotations

from typing import Any, Mapping

from strata.core.types import VirtualMicroseconds


class BaseWorkload:
    """Abstract base class for workload generators."""

    def __init__(self, parameters: Mapping[str, Any] | None = None) -> None:
        self.parameters = dict(parameters or {})

    def generate_events(self, engine: Any) -> None:
        """Schedule workload operations directly into the simulation engine queue."""
        raise NotImplementedError("Subclasses must implement generate_events()")
