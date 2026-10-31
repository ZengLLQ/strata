"""Base classes and contracts for the fault injection subsystem."""

from __future__ import annotations

from typing import Any, Mapping

from strata.core.types import FaultPhase, VirtualMicroseconds


class BaseFault:
    """Abstract base class for all injected faults.
    
    Distinguishes scheduled declaration from actual runtime application.
    """

    def __init__(
        self,
        fault_id: str,
        fault_type: str,
        target: str,
        trigger_time_us: VirtualMicroseconds,
        duration_us: VirtualMicroseconds | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        self.fault_id = fault_id
        self.fault_type = fault_type
        self.target = target
        self.trigger_time_us = trigger_time_us
        self.duration_us = duration_us
        self.parameters = dict(parameters or {})
        self._phase: FaultPhase = FaultPhase.SCHEDULED
        self.applied_at_us: VirtualMicroseconds | None = None
        self.execution_evidence: dict[str, Any] = {}

    @property
    def phase(self) -> FaultPhase:
        """Current lifecycle phase of the fault."""
        return self._phase

    def mark_applied(self, now_us: VirtualMicroseconds, evidence: Mapping[str, Any]) -> None:
        """Record successful application of the fault."""
        self._phase = FaultPhase.APPLIED
        self.applied_at_us = now_us
        self.execution_evidence = dict(evidence)

    def mark_failed(self, error_message: str) -> None:
        """Record failure during fault application."""
        self._phase = FaultPhase.FAILED
        self.execution_evidence = {"error": error_message}
