"""Concrete invariant evaluators for convergence, fault observation, and health."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from strata.core.types import InvariantVerdict, NodeState
from strata.invariants.base import BaseInvariant, InvariantResult
from strata.simulation.events import BaseEvent, FaultAppliedEvent


class StateConvergenceInvariant(BaseInvariant):
    """Asserts that all operational (ONLINE) nodes reach identical state at simulation end."""

    def __init__(
        self,
        invariant_id: str = "inv_state_convergence",
        description: str = "Active nodes must converge to equivalent key-value states",
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            invariant_id=invariant_id,
            invariant_type="state_convergence",
            description=description,
            parameters=parameters,
        )

    def evaluate(self, engine: Any, events: Sequence[BaseEvent]) -> InvariantResult:
        online_nodes = [
            node for node in engine.nodes.values()
            if hasattr(node, "get_state_snapshot") and node.state == NodeState.ONLINE
        ]

        if not online_nodes:
            return InvariantResult(
                invariant_id=self.invariant_id,
                invariant_type=self.invariant_type,
                verdict=InvariantVerdict.INCONCLUSIVE,
                explanation="No online nodes available to evaluate state convergence.",
                relevant_event_ids=[],
                details={"online_node_count": 0},
            )

        # Reference baseline is the first online node
        baseline_node = online_nodes[0]
        baseline_state = baseline_node.get_state_snapshot()
        divergent_nodes: dict[str, dict[str, Any]] = {}

        for node in online_nodes[1:]:
            node_state = node.get_state_snapshot()
            if node_state != baseline_state:
                divergent_nodes[node.node_id] = {
                    "baseline_node": baseline_node.node_id,
                    "baseline_keys": list(baseline_state.keys()),
                    "divergent_keys": list(node_state.keys()),
                }

        # Collect event IDs of write operations for context
        write_event_ids = [
            e.sequence_id for e in events
            if e.event_type == "workload.operation"
        ]

        if divergent_nodes:
            return InvariantResult(
                invariant_id=self.invariant_id,
                invariant_type=self.invariant_type,
                verdict=InvariantVerdict.VIOLATED,
                explanation=(
                    f"State divergence detected across {len(divergent_nodes)} online node(s). "
                    f"Nodes did not converge to the same state."
                ),
                relevant_event_ids=write_event_ids,
                details={
                    "baseline_node": baseline_node.node_id,
                    "baseline_state": baseline_state,
                    "divergences": divergent_nodes,
                },
            )

        return InvariantResult(
            invariant_id=self.invariant_id,
            invariant_type=self.invariant_type,
            verdict=InvariantVerdict.PASSED,
            explanation=(
                f"All {len(online_nodes)} online nodes converged to identical state "
                f"({len(baseline_state)} keys replicated)."
            ),
            relevant_event_ids=write_event_ids,
            details={
                "converged_node_ids": [n.node_id for n in online_nodes],
                "shared_state": baseline_state,
            },
        )


class FaultObservedInvariant(BaseInvariant):
    """Asserts that all scheduled faults in the experiment were actually applied and recorded."""

    def __init__(
        self,
        invariant_id: str = "inv_fault_observed",
        description: str = "All scheduled faults must generate an applied audit record",
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            invariant_id=invariant_id,
            invariant_type="fault_observed",
            description=description,
            parameters=parameters,
        )

    def evaluate(self, engine: Any, events: Sequence[BaseEvent]) -> InvariantResult:
        scheduled_fault_ids = {f.id for f in engine.experiment.faults}
        applied_fault_events = [
            e for e in events
            if isinstance(e, FaultAppliedEvent) or e.event_type == "fault.applied"
        ]
        applied_fault_ids = {
            e.payload.get("fault_id") for e in applied_fault_events
            if e.payload.get("fault_id")
        }

        missing_faults = scheduled_fault_ids - applied_fault_ids
        relevant_ids = [e.sequence_id for e in applied_fault_events]

        if missing_faults:
            return InvariantResult(
                invariant_id=self.invariant_id,
                invariant_type=self.invariant_type,
                verdict=InvariantVerdict.VIOLATED,
                explanation=f"Scheduled faults were not applied: {sorted(missing_faults)}",
                relevant_event_ids=relevant_ids,
                details={
                    "scheduled": sorted(scheduled_fault_ids),
                    "applied": sorted(applied_fault_ids),
                    "missing": sorted(missing_faults),
                },
            )

        return InvariantResult(
            invariant_id=self.invariant_id,
            invariant_type=self.invariant_type,
            verdict=InvariantVerdict.PASSED,
            explanation=f"All {len(scheduled_fault_ids)} scheduled faults were applied and verified.",
            relevant_event_ids=relevant_ids,
            details={
                "applied_fault_ids": sorted(applied_fault_ids),
            },
        )


class NoPanicInvariant(BaseInvariant):
    """Asserts that no node crashed unexpectedly or threw unhandled internal exceptions."""

    def __init__(
        self,
        invariant_id: str = "inv_no_panic",
        description: str = "Engine and nodes must complete without unhandled exceptions",
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            invariant_id=invariant_id,
            invariant_type="no_panic",
            description=description,
            parameters=parameters,
        )

    def evaluate(self, engine: Any, events: Sequence[BaseEvent]) -> InvariantResult:
        error_events = [
            e for e in events
            if "error" in e.event_type or e.payload.get("error") is not None
        ]

        if error_events:
            return InvariantResult(
                invariant_id=self.invariant_id,
                invariant_type=self.invariant_type,
                verdict=InvariantVerdict.VIOLATED,
                explanation=f"Encountered {len(error_events)} error events during simulation execution.",
                relevant_event_ids=[e.sequence_id for e in error_events],
                details={"errors": [e.to_dict() for e in error_events]},
            )

        return InvariantResult(
            invariant_id=self.invariant_id,
            invariant_type=self.invariant_type,
            verdict=InvariantVerdict.PASSED,
            explanation="Simulation execution completed cleanly without unhandled panics or errors.",
            relevant_event_ids=[],
            details={"total_events_checked": len(events)},
        )


class PartitionIsolationInvariant(BaseInvariant):
    """Asserts that zero messages crossed an active network partition boundary."""

    def __init__(
        self,
        invariant_id: str = "inv_partition_isolation",
        description: str = "No messages delivered between partitioned node groups during partition window",
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            invariant_id=invariant_id,
            invariant_type="partition_isolation",
            description=description,
            parameters=parameters,
        )

    def evaluate(self, engine: Any, events: Sequence[BaseEvent]) -> InvariantResult:
        # Find all partition events
        partition_events = [
            e for e in events
            if e.event_type == "fault.applied" and e.payload.get("fault_type") == "network_partition"
        ]

        if not partition_events:
            return InvariantResult(
                invariant_id=self.invariant_id,
                invariant_type=self.invariant_type,
                verdict=InvariantVerdict.SKIPPED,
                explanation="No network partition faults were applied in this experiment.",
                relevant_event_ids=[],
            )

        violating_events: list[int] = []

        for p_event in partition_events:
            start_us = p_event.timestamp_us
            group_a = set(p_event.payload.get("evidence", {}).get("group_a", []))
            group_b = set(p_event.payload.get("evidence", {}).get("group_b", []))

            # Find matching heal event
            heal_events = [
                e for e in events
                if e.event_type == "fault.applied"
                and e.payload.get("fault_type") == "network_heal"
                and e.timestamp_us >= start_us
            ]
            end_us = heal_events[0].timestamp_us if heal_events else float("inf")

            # Check all message delivery events within [start_us, end_us]
            for e in events:
                if e.event_type == "network.message_delivery" and start_us <= e.timestamp_us < end_us:
                    src = e.source
                    tgt = e.target
                    if (src in group_a and tgt in group_b) or (src in group_b and tgt in group_a):
                        violating_events.append(e.sequence_id)

        if violating_events:
            return InvariantResult(
                invariant_id=self.invariant_id,
                invariant_type=self.invariant_type,
                verdict=InvariantVerdict.VIOLATED,
                explanation=(
                    f"Partition isolation violated: {len(violating_events)} message(s) "
                    f"were delivered across an active partition boundary."
                ),
                relevant_event_ids=violating_events,
                details={"violating_delivery_count": len(violating_events)},
            )

        return InvariantResult(
            invariant_id=self.invariant_id,
            invariant_type=self.invariant_type,
            verdict=InvariantVerdict.PASSED,
            explanation="Partition isolation preserved: zero messages delivered across partition boundaries.",
            relevant_event_ids=[e.sequence_id for e in partition_events],
            details={"partitions_evaluated": len(partition_events)},
        )
