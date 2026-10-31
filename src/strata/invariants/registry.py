"""Registry for invariant evaluators."""

from __future__ import annotations

from typing import Type

from strata.core.errors import InvariantError
from strata.core.experiment import InvariantConfig
from strata.invariants.base import BaseInvariant
from strata.invariants.convergence import (
    FaultObservedInvariant,
    NoPanicInvariant,
    PartitionIsolationInvariant,
    StateConvergenceInvariant,
)


class InvariantRegistry:
    """Registry maintaining available invariant evaluator implementations."""

    _REGISTRY: dict[str, Type[BaseInvariant]] = {
        "state_convergence": StateConvergenceInvariant,
        "fault_observed": FaultObservedInvariant,
        "no_panic": NoPanicInvariant,
        "partition_isolation": PartitionIsolationInvariant,
    }

    @classmethod
    def register(cls, invariant_type: str, inv_cls: Type[BaseInvariant]) -> None:
        """Register a new invariant evaluator."""
        cls._REGISTRY[invariant_type] = inv_cls

    @classmethod
    def create_from_config(cls, config: InvariantConfig) -> BaseInvariant:
        """Instantiate an invariant from an InvariantConfig model."""
        inv_cls = cls._REGISTRY.get(config.invariant_type)
        if inv_cls is None:
            supported = sorted(cls._REGISTRY.keys())
            raise InvariantError(
                f"Unsupported invariant type '{config.invariant_type}'. Supported types: {supported}"
            )

        return inv_cls(
            invariant_id=config.id,
            description=config.description,
            parameters=config.parameters,
        )
