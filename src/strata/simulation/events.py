"""Structured event definitions and serialization for discrete-event simulation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from strata.core.types import EventPriority, EventSequenceId, NodeState, VirtualMicroseconds


@dataclass(frozen=True, slots=True)
class BaseEvent:
    """Immutable discrete event dispatched through the simulation engine."""

    sequence_id: EventSequenceId
    timestamp_us: VirtualMicroseconds
    priority: EventPriority
    event_type: str
    source: str | None = None
    target: str | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    wall_clock_iso: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert event into a JSON-serializable dictionary."""
        return {
            "sequence_id": self.sequence_id,
            "timestamp_us": self.timestamp_us,
            "priority": int(self.priority),
            "priority_name": self.priority.name,
            "event_type": self.event_type,
            "source": self.source,
            "target": self.target,
            "payload": dict(self.payload),
            "wall_clock_iso": self.wall_clock_iso,
        }

    def __lt__(self, other: BaseEvent) -> bool:
        """Total ordering comparison for heap operations:
        
        Ordered by (timestamp_us, priority, sequence_id).
        """
        if self.timestamp_us != other.timestamp_us:
            return self.timestamp_us < other.timestamp_us
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.sequence_id < other.sequence_id


@dataclass(frozen=True, slots=True)
class MessageDeliveryEvent(BaseEvent):
    """Event representing the scheduled arrival of a network message."""

    @classmethod
    def create(
        cls,
        sequence_id: EventSequenceId,
        timestamp_us: VirtualMicroseconds,
        source: str,
        target: str,
        message_type: str,
        data: Mapping[str, Any],
        priority: EventPriority = EventPriority.NETWORK_DELIVERY,
    ) -> MessageDeliveryEvent:
        return cls(
            sequence_id=sequence_id,
            timestamp_us=timestamp_us,
            priority=priority,
            event_type="network.message_delivery",
            source=source,
            target=target,
            payload={"message_type": message_type, "data": dict(data)},
        )


@dataclass(frozen=True, slots=True)
class NodeStateChangeEvent(BaseEvent):
    """Event recording an operational state transition of a node."""

    @classmethod
    def create(
        cls,
        sequence_id: EventSequenceId,
        timestamp_us: VirtualMicroseconds,
        node_id: str,
        previous_state: NodeState,
        new_state: NodeState,
        reason: str,
        priority: EventPriority = EventPriority.NODE_LIFECYCLE,
    ) -> NodeStateChangeEvent:
        return cls(
            sequence_id=sequence_id,
            timestamp_us=timestamp_us,
            priority=priority,
            event_type="node.state_change",
            source="system",
            target=node_id,
            payload={
                "previous_state": previous_state.value,
                "new_state": new_state.value,
                "reason": reason,
            },
        )


@dataclass(frozen=True, slots=True)
class FaultAppliedEvent(BaseEvent):
    """Event recording the successful application of an injected failure."""

    @classmethod
    def create(
        cls,
        sequence_id: EventSequenceId,
        timestamp_us: VirtualMicroseconds,
        fault_id: str,
        fault_type: str,
        target: str,
        evidence: Mapping[str, Any],
        priority: EventPriority = EventPriority.SYSTEM_FAULT,
    ) -> FaultAppliedEvent:
        return cls(
            sequence_id=sequence_id,
            timestamp_us=timestamp_us,
            priority=priority,
            event_type="fault.applied",
            source="fault_injector",
            target=target,
            payload={
                "fault_id": fault_id,
                "fault_type": fault_type,
                "evidence": dict(evidence),
            },
        )


@dataclass(frozen=True, slots=True)
class WorkloadOperationEvent(BaseEvent):
    """Event recording client operation invocation and outcome."""

    @classmethod
    def create(
        cls,
        sequence_id: EventSequenceId,
        timestamp_us: VirtualMicroseconds,
        target_node: str,
        operation_id: str,
        op_type: str,
        key: str,
        value: Any,
        priority: EventPriority = EventPriority.WORKLOAD_INGESTION,
        extra: Mapping[str, Any] | None = None,
    ) -> WorkloadOperationEvent:
        payload_data: dict[str, Any] = {
            "operation_id": operation_id,
            "op_type": op_type,
            "key": key,
            "value": value,
        }
        if extra:
            payload_data.update(extra)
        return cls(
            sequence_id=sequence_id,
            timestamp_us=timestamp_us,
            priority=priority,
            event_type="workload.operation",
            source="workload_generator",
            target=target_node,
            payload=payload_data,
        )
