"""Node crash and restart fault implementations."""

from __future__ import annotations

from typing import Any, Mapping

from strata.core.errors import FaultApplicationError
from strata.core.types import EventPriority, NodeState, VirtualMicroseconds
from strata.faults.base import BaseFault
from strata.simulation.events import FaultAppliedEvent, NodeStateChangeEvent


class NodeCrashFault(BaseFault):
    """Fault that transitions a target node into the OFFLINE (crashed) state."""

    def __init__(
        self,
        fault_id: str,
        target: str,
        trigger_time_us: VirtualMicroseconds,
        duration_us: VirtualMicroseconds | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            fault_id=fault_id,
            fault_type="node_crash",
            target=target,
            trigger_time_us=trigger_time_us,
            duration_us=duration_us,
            parameters=parameters,
        )

    def apply(self, engine: Any, now_us: VirtualMicroseconds) -> dict[str, Any]:
        """Execute node crash against the target node."""
        node = engine.nodes.get(self.target)
        if node is None:
            raise FaultApplicationError(f"Cannot crash unknown node '{self.target}'")

        previous_state = node.state
        node.crash(now_us)

        # Emit node state transition event
        state_event = NodeStateChangeEvent.create(
            sequence_id=engine.next_sequence_id(),
            timestamp_us=now_us,
            node_id=self.target,
            previous_state=previous_state,
            new_state=NodeState.OFFLINE,
            reason=f"fault_injection:{self.fault_id}",
        )
        engine.record_event(state_event)

        restart_time_us: VirtualMicroseconds | None = None
        if self.duration_us is not None and self.duration_us > 0:
            restart_time_us = now_us + self.duration_us
            restart_fault = NodeRestartFault(
                fault_id=f"{self.fault_id}_restart",
                target=self.target,
                trigger_time_us=restart_time_us,
            )
            engine.schedule_fault(restart_fault)

        evidence = {
            "node_id": self.target,
            "previous_state": previous_state.value,
            "new_state": NodeState.OFFLINE.value,
            "restart_scheduled_at_us": restart_time_us,
        }
        self.mark_applied(now_us, evidence)

        fault_event = FaultAppliedEvent.create(
            sequence_id=engine.next_sequence_id(),
            timestamp_us=now_us,
            fault_id=self.fault_id,
            fault_type=self.fault_type,
            target=self.target,
            evidence=evidence,
        )
        engine.record_event(fault_event)

        return evidence


class NodeRestartFault(BaseFault):
    """Fault that recovers a crashed node back to the ONLINE state."""

    def __init__(
        self,
        fault_id: str,
        target: str,
        trigger_time_us: VirtualMicroseconds,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            fault_id=fault_id,
            fault_type="node_restart",
            target=target,
            trigger_time_us=trigger_time_us,
            duration_us=None,
            parameters=parameters,
        )

    def apply(self, engine: Any, now_us: VirtualMicroseconds) -> dict[str, Any]:
        """Execute node recovery against target node."""
        node = engine.nodes.get(self.target)
        if node is None:
            raise FaultApplicationError(f"Cannot restart unknown node '{self.target}'")

        previous_state = node.state
        node.recover(now_us)

        state_event = NodeStateChangeEvent.create(
            sequence_id=engine.next_sequence_id(),
            timestamp_us=now_us,
            node_id=self.target,
            previous_state=previous_state,
            new_state=NodeState.ONLINE,
            reason=f"fault_recovery:{self.fault_id}",
        )
        engine.record_event(state_event)

        evidence = {
            "node_id": self.target,
            "previous_state": previous_state.value,
            "new_state": NodeState.ONLINE.value,
        }
        self.mark_applied(now_us, evidence)

        fault_event = FaultAppliedEvent.create(
            sequence_id=engine.next_sequence_id(),
            timestamp_us=now_us,
            fault_id=self.fault_id,
            fault_type=self.fault_type,
            target=self.target,
            evidence=evidence,
        )
        engine.record_event(fault_event)

        return evidence
