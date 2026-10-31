"""Abstract contracts and protocols establishing subsystem boundaries."""

from __future__ import annotations

from typing import Any, Mapping, Protocol, Sequence, runtime_checkable
from strata.core.types import (
    EventPriority,
    EventSequenceId,
    FaultPhase,
    InvariantVerdict,
    NodeId,
    NodeState,
    VirtualMicroseconds,
)


@runtime_checkable
class SimulationClock(Protocol):
    """Protocol for virtual clock implementations."""

    @property
    def current_time_us(self) -> VirtualMicroseconds:
        """Return the current virtual time in microseconds."""
        ...

    def advance_to(self, target_time_us: VirtualMicroseconds) -> None:
        """Advance the virtual clock to the specified target time."""
        ...


@runtime_checkable
class EventContract(Protocol):
    """Protocol governing all discrete events dispatched through the engine."""

    @property
    def sequence_id(self) -> EventSequenceId:
        """Monotonically assigned sequence identifier."""
        ...

    @property
    def timestamp_us(self) -> VirtualMicroseconds:
        """Virtual execution timestamp in microseconds."""
        ...

    @property
    def priority(self) -> EventPriority:
        """Scheduling priority tier."""
        ...

    @property
    def event_type(self) -> str:
        """Distinguishable event type identifier."""
        ...

    @property
    def source(self) -> str | None:
        """Originating entity or component."""
        ...

    @property
    def target(self) -> str | None:
        """Destination entity or component."""
        ...

    @property
    def payload(self) -> Mapping[str, Any]:
        """Structured event payload."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Serialize event into a JSON-serializable dictionary."""
        ...


@runtime_checkable
class SimulatedNodeContract(Protocol):
    """Protocol defining the lifecycle and message handling of a simulated node."""

    @property
    def node_id(self) -> NodeId:
        """Unique node identifier."""
        ...

    @property
    def state(self) -> NodeState:
        """Current operational lifecycle state."""
        ...

    def initialize(self) -> None:
        """Initialize internal state machine and handlers."""
        ...

    def on_message(
        self,
        sender: NodeId,
        message_type: str,
        payload: Mapping[str, Any],
        now_us: VirtualMicroseconds,
    ) -> Sequence[EventContract]:
        """Process an incoming message and return any scheduled follow-up events."""
        ...

    def crash(self, now_us: VirtualMicroseconds) -> None:
        """Forcefully crash the node, transitioning to OFFLINE."""
        ...

    def recover(self, now_us: VirtualMicroseconds) -> None:
        """Recover the node from crash, restoring basic operation."""
        ...


@runtime_checkable
class FaultContract(Protocol):
    """Protocol governing fault definitions and injection mechanisms."""

    @property
    def fault_id(self) -> str:
        """Unique identifier for this fault instance."""
        ...

    @property
    def fault_type(self) -> str:
        """Canonical fault type identifier."""
        ...

    @property
    def target(self) -> str:
        """Target entity identifier (e.g. node_id or link)."""
        ...

    @property
    def trigger_time_us(self) -> VirtualMicroseconds:
        """Virtual time when this fault should be applied."""
        ...

    @property
    def phase(self) -> FaultPhase:
        """Current lifecycle phase of the fault."""
        ...

    def apply(self, engine: Any, now_us: VirtualMicroseconds) -> dict[str, Any]:
        """Apply the fault to the target and return execution evidence."""
        ...


@runtime_checkable
class ServiceAdapterContract(Protocol):
    """Protocol governing real-system external service adapters."""

    @property
    def adapter_name(self) -> str:
        """Distinguishable identifier for this adapter implementation."""
        ...

    def setup(self, timeout_seconds: float = 30.0) -> None:
        """Initialize the integration environment and verify connectivity."""
        ...

    def health_check(self, timeout_seconds: float = 5.0) -> bool:
        """Verify that all target services in the cluster are responsive."""
        ...

    def execute_workload(
        self,
        workload_config: Any,
        start_time_ns: int,
    ) -> Sequence[EventContract]:
        """Execute a workload against target services and return observed event records."""
        ...

    def inject_fault(
        self,
        fault_config: Any,
        now_ns: int,
    ) -> EventContract:
        """Apply a real-world fault to target external services and return evidence event."""
        ...

    def collect_results(self) -> dict[str, Any]:
        """Gather final cluster state snapshots and metrics."""
        ...

    def get_environment_metadata(self) -> dict[str, Any]:
        """Return system and runtime environment metadata."""
        ...

    def get_determinism_limitations(self) -> dict[str, str]:
        """Return explicit documentation of non-deterministic boundaries."""
        ...

    def teardown(self) -> None:
        """Clean up all external integration resources and reset state."""
        ...
