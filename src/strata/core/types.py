"""Core type definitions, enums, and identifier aliases for Strata."""

from __future__ import annotations

from enum import Enum, IntEnum
from typing import NewType

# Strict type aliases
NodeId = str
EventSequenceId = int
VirtualMicroseconds = int


class ExecutionMode(str, Enum):
    """Execution paradigm supported by the framework."""

    SIMULATION = "simulation"
    INTEGRATION = "integration"


class RunStatus(str, Enum):
    """Lifecycle status of an experiment run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    INTERRUPTED = "interrupted"


class NodeState(str, Enum):
    """Operational state machine of a simulated node."""

    INITIALIZING = "initializing"
    ONLINE = "online"
    OFFLINE = "offline"  # Crashed or partitioned from execution
    RECOVERING = "recovering"  # Rebooting / state rebuilding


class FaultPhase(str, Enum):
    """Lifecycle phase of an injected fault."""

    SCHEDULED = "scheduled"
    APPLIED = "applied"
    OBSERVED = "observed"
    FAILED = "failed"


class InvariantVerdict(str, Enum):
    """Verdict rendered by an invariant evaluator."""

    PASSED = "passed"
    VIOLATED = "violated"
    INCONCLUSIVE = "inconclusive"
    SKIPPED = "skipped"


class EventPriority(IntEnum):
    """Priority tiers for discrete-event scheduling.
    
    Lower integer values take precedence in scheduling when timestamps match.
    """

    SYSTEM_FAULT = 0
    NODE_LIFECYCLE = 1
    NETWORK_DELIVERY = 2
    WORKLOAD_INGESTION = 3
    DIAGNOSTIC = 4
