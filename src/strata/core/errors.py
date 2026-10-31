"""Structured exception hierarchy for the Strata framework."""

from __future__ import annotations


class StrataError(Exception):
    """Root exception for all Strata errors."""

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            detail_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({detail_str})"
        return self.message


class ConfigurationError(StrataError):
    """Raised when an experiment definition fails validation or constraint checks."""


class TopologyError(ConfigurationError):
    """Raised when node references, link definitions, or topology constraints are invalid."""


class SimulationError(StrataError):
    """Base error for runtime issues during discrete-event simulation."""


class RunawaySimulationError(SimulationError):
    """Raised when simulation exceeds maximum allowed events or runaway loops are detected."""


class SimulationTimeoutError(SimulationError):
    """Raised when simulation exceeds maximum allowed wall-clock execution time."""


class NodeStateError(SimulationError):
    """Raised on invalid node state transitions or operations on crashed nodes."""


class UnroutableMessageError(SimulationError):
    """Raised when a message cannot be delivered due to unknown topology or dead links."""


class FaultError(StrataError):
    """Base error for fault injection definition and execution issues."""


class UnsupportedFaultError(FaultError):
    """Raised when an experiment requests an unimplemented or unsupported fault type."""


class FaultApplicationError(FaultError):
    """Raised when applying a fault to a node or network fails at runtime."""


class InvariantError(StrataError):
    """Base error for invariant evaluation failures."""


class InvariantEvaluationError(InvariantError):
    """Raised when an invariant evaluator encounters malformed evidence or engine failure."""


class AdapterError(StrataError):
    """Base error for external service adapter failures."""


class HealthCheckFailedError(AdapterError):
    """Raised when an external service fails health check probes."""


class DestructiveActionRefusalError(AdapterError):
    """Raised when a destructive integration action is attempted without explicit authorization."""


class EnvironmentSetupError(AdapterError):
    """Raised when setting up an external integration environment fails."""


class StorageError(StrataError):
    """Base error for metadata persistence and artifact management."""


class ArtifactIntegrityError(StorageError):
    """Raised when an artifact checksum or manifest verification fails."""
