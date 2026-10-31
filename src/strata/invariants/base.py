"""Base classes and result contracts for the invariant evaluation engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from strata.core.types import InvariantVerdict
from strata.simulation.events import BaseEvent


@dataclass(frozen=True, slots=True)
class InvariantResult:
    """Auditable result of evaluating a system invariant against experiment history."""

    invariant_id: str
    invariant_type: str
    verdict: InvariantVerdict
    explanation: str
    evaluator_version: str = "1.0.0"
    relevant_event_ids: list[int] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert invariant result to dictionary."""
        return {
            "invariant_id": self.invariant_id,
            "invariant_type": self.invariant_type,
            "verdict": self.verdict.value,
            "explanation": self.explanation,
            "evaluator_version": self.evaluator_version,
            "relevant_event_ids": list(self.relevant_event_ids),
            "details": dict(self.details),
        }


class BaseInvariant:
    """Abstract base class for all invariant evaluators."""

    def __init__(
        self,
        invariant_id: str,
        invariant_type: str,
        description: str = "",
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        self.invariant_id = invariant_id
        self.invariant_type = invariant_type
        self.description = description
        self.parameters = dict(parameters or {})

    def evaluate(
        self,
        engine: Any,
        events: Sequence[BaseEvent],
    ) -> InvariantResult:
        """Evaluate the invariant against the completed experiment state and event log."""
        raise NotImplementedError("Subclasses must implement evaluate()")
