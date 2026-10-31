"""Deterministic discrete-event simulation engine for Strata."""

from __future__ import annotations

import random
import time
from typing import Any, Callable, Sequence
import uuid

from strata.core.errors import (
    RunawaySimulationError,
    SimulationError,
    SimulationTimeoutError,
)
from strata.core.experiment import ExperimentDefinition
from strata.core.types import (
    EventPriority,
    EventSequenceId,
    ExecutionMode,
    NodeId,
    NodeState,
    RunStatus,
    VirtualMicroseconds,
)
from strata.faults.base import BaseFault
from strata.faults.registry import FaultRegistry
from strata.invariants.base import InvariantResult
from strata.invariants.registry import InvariantRegistry
from strata.simulation.clock import VirtualClock
from strata.simulation.events import (
    BaseEvent,
    MessageDeliveryEvent,
    NodeStateChangeEvent,
    WorkloadOperationEvent,
)
from strata.simulation.consensus.raft import RaftNode, RaftRole
from strata.simulation.network import SimulatedNetwork
from strata.simulation.node import BaseSimulatedNode, ReplicatedKVNode
from strata.simulation.queue import PriorityEventQueue
from strata.workloads.kv import ReplicatedKVWorkload


class RunResult:
    """Summary of a completed experiment simulation run."""

    def __init__(
        self,
        run_id: str,
        experiment_id: str,
        status: RunStatus,
        seed: int,
        events_processed: int,
        final_virtual_time_us: VirtualMicroseconds,
        wall_clock_duration_s: float,
        invariant_results: list[InvariantResult],
        events: list[BaseEvent],
        node_states: dict[str, Any] | None = None,
        execution_mode: ExecutionMode = ExecutionMode.SIMULATION,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.run_id = run_id
        self.experiment_id = experiment_id
        self.status = status
        self.seed = seed
        self.events_processed = events_processed
        self.final_virtual_time_us = final_virtual_time_us
        self.wall_clock_duration_s = wall_clock_duration_s
        self.invariant_results = invariant_results
        self.events = events
        self.node_states: dict[str, Any] = node_states or {}
        self.execution_mode = execution_mode
        self.metadata = metadata or {}
        self.all_invariants_passed = all(
            r.verdict.value == "passed" for r in invariant_results
        ) if invariant_results else True

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "experiment_id": self.experiment_id,
            "status": self.status.value,
            "execution_mode": self.execution_mode.value,
            "seed": self.seed,
            "events_processed": self.events_processed,
            "final_virtual_time_us": self.final_virtual_time_us,
            "wall_clock_duration_s": round(self.wall_clock_duration_s, 6),
            "all_invariants_passed": self.all_invariants_passed,
            "invariant_results": [r.to_dict() for r in self.invariant_results],
            "node_states": self.node_states,
            "metadata": self.metadata,
        }


class DeterministicSimulationEngine:
    """Deterministic simulation engine driving virtual time, nodes, and network events."""

    def __init__(
        self,
        experiment: ExperimentDefinition,
        run_id: str | None = None,
        event_callback: Callable[[BaseEvent], None] | None = None,
    ) -> None:
        self.experiment = experiment
        self.run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
        self.seed = experiment.execution.seed
        self.event_callback = event_callback

        # Dedicated, isolated pseudo-random generator
        self.rng = random.Random(self.seed)

        # Discrete-event mechanics
        self.clock = VirtualClock(0)
        self.queue = PriorityEventQueue()
        self._sequence_counter: EventSequenceId = 0

        # Subsystems
        all_node_ids = {node.id for node in experiment.topology.nodes}
        self.network = SimulatedNetwork(
            config=experiment.topology.network,
            valid_nodes=all_node_ids,
            rng=self.rng,
        )

        # Build simulated nodes (ReplicatedKVNode or RaftNode)
        self.nodes: dict[NodeId, BaseSimulatedNode] = {}
        all_peers = sorted(all_node_ids)
        is_raft_cluster = (
            experiment.workload.workload_type == "raft_kv"
            or any(n.role == "raft_node" for n in experiment.topology.nodes)
        )

        for node_cfg in experiment.topology.nodes:
            if is_raft_cluster or node_cfg.role == "raft_node":
                peers = [nid for nid in all_peers if nid != node_cfg.id]
                election_to = node_cfg.parameters.get("election_timeout_us", 150000)
                heartbeat_int = node_cfg.parameters.get("heartbeat_interval_us", 50000)
                self.nodes[node_cfg.id] = RaftNode(
                    node_id=node_cfg.id,
                    peers=peers,
                    initial_state=node_cfg.initial_state,
                    election_timeout_us=election_to,
                    heartbeat_interval_us=heartbeat_int,
                    parameters=node_cfg.parameters,
                )
            else:
                self.nodes[node_cfg.id] = ReplicatedKVNode(
                    node_id=node_cfg.id,
                    peers=all_peers,
                    role=node_cfg.role,
                    initial_state=node_cfg.initial_state,
                    parameters=node_cfg.parameters,
                )

        # Registered faults to apply
        self.faults: list[BaseFault] = [
            FaultRegistry.create_from_config(f_cfg) for f_cfg in experiment.faults
        ]

        # Invariant evaluators
        self.invariants = [
            InvariantRegistry.create_from_config(inv_cfg) for inv_cfg in experiment.invariants
        ]

        # Recorded history of dispatched events
        self.event_history: list[BaseEvent] = []

    def next_sequence_id(self) -> EventSequenceId:
        """Atomically increment and return the next sequence identifier."""
        self._sequence_counter += 1
        return self._sequence_counter

    def schedule_event(self, event: BaseEvent) -> None:
        """Insert an event into the deterministic priority queue."""
        self.queue.push(event)

    def schedule_fault(self, fault: BaseFault) -> None:
        """Schedule a fault to be applied at its defined trigger timestamp."""
        # Wrap fault execution into a system event
        event = BaseEvent(
            sequence_id=self.next_sequence_id(),
            timestamp_us=fault.trigger_time_us,
            priority=EventPriority.SYSTEM_FAULT,
            event_type="fault.schedule",
            source="fault_scheduler",
            target=fault.target,
            payload={"fault_instance": fault},
        )
        self.schedule_event(event)

    def record_event(self, event: BaseEvent) -> None:
        """Log an event to the run history and deliver to active stream subscribers."""
        self.event_history.append(event)
        if self.event_callback is not None:
            self.event_callback(event)

    def run(self) -> RunResult:
        """Execute the deterministic simulation to completion or limit."""
        start_wall_clock = time.perf_counter()
        events_processed = 0

        # 1. Initialize all simulated nodes
        for node in self.nodes.values():
            node.initialize()
            if hasattr(node, "check_timers") and hasattr(node, "election_timeout_us"):
                init_tick = BaseEvent(
                    sequence_id=self.next_sequence_id(),
                    timestamp_us=node.election_timeout_us,
                    priority=EventPriority.DIAGNOSTIC,
                    event_type="node.timer_tick",
                    target=node.node_id,
                    payload={},
                )
                self.schedule_event(init_tick)

        # 2. Schedule all declared faults
        for fault in self.faults:
            self.schedule_fault(fault)

        # 3. Schedule workload operations
        if self.experiment.workload.operations_count > 0:
            workload = ReplicatedKVWorkload(self.experiment.workload)
            workload.generate_events(self)

        status = RunStatus.RUNNING
        limits = self.experiment.limits

        try:
            while self.queue:
                # Check wall-clock timeout guard
                elapsed_wall = time.perf_counter() - start_wall_clock
                if elapsed_wall > limits.wall_clock_timeout_seconds:
                    status = RunStatus.TIMEOUT
                    raise SimulationTimeoutError(
                        f"Simulation exceeded wall-clock limit of {limits.wall_clock_timeout_seconds}s"
                    )

                # Check event iteration runaway guard
                if events_processed >= limits.max_events:
                    status = RunStatus.FAILED
                    raise RunawaySimulationError(
                        f"Simulation exceeded maximum event limit of {limits.max_events} events"
                    )

                event = self.queue.pop()

                # Check virtual time ceiling
                if event.timestamp_us > limits.max_virtual_time_us:
                    # Simulation boundary reached
                    break

                # Advance virtual clock monotonically
                self.clock.advance_to(event.timestamp_us)
                events_processed += 1
                self.record_event(event)

                # Dispatch event according to its event_type
                self._dispatch_event(event)

            status = RunStatus.COMPLETED

        except Exception as exc:
            if status == RunStatus.RUNNING:
                status = RunStatus.FAILED
            raise exc

        finally:
            wall_duration = time.perf_counter() - start_wall_clock

        # 4. Evaluate invariants against the completed run history
        invariant_results: list[InvariantResult] = []
        for inv in self.invariants:
            result = inv.evaluate(self, self.event_history)
            invariant_results.append(result)

        # 5. Capture final node state snapshots
        final_node_states: dict[str, Any] = {
            node_id: node.get_state_snapshot()
            for node_id, node in self.nodes.items()
            if hasattr(node, "get_state_snapshot")
        }

        return RunResult(
            run_id=self.run_id,
            experiment_id=self.experiment.metadata.id,
            status=status,
            seed=self.seed,
            events_processed=events_processed,
            final_virtual_time_us=self.clock.current_time_us,
            wall_clock_duration_s=wall_duration,
            invariant_results=invariant_results,
            events=self.event_history,
            node_states=final_node_states,
        )

    def _dispatch_event(self, event: BaseEvent) -> None:
        """Route event to the appropriate subsystem handler."""
        now_us = event.timestamp_us

        if event.event_type == "fault.schedule":
            fault_instance: BaseFault = event.payload["fault_instance"]
            fault_instance.apply(self, now_us)

        elif event.event_type == "workload.operation":
            target_node_id = str(event.target)
            node = self.nodes.get(target_node_id)
            if node is not None:
                actual_target = node
                if hasattr(node, "role") and node.role != RaftRole.LEADER:
                    leader_node = next(
                        (n for n in self.nodes.values() if getattr(n, "role", None) == RaftRole.LEADER and n.state == NodeState.ONLINE),
                        None,
                    )
                    if leader_node is not None:
                        actual_target = leader_node
                        target_node_id = leader_node.node_id

                outbound = actual_target.handle_message(
                    sender="client",
                    message_type=event.payload["op_type"],
                    payload=event.payload,
                    now_us=now_us,
                )
                self._route_outbound_messages(target_node_id, outbound, now_us)

        elif event.event_type == "node.timer_tick":
            target_node_id = str(event.target)
            node = self.nodes.get(target_node_id)
            if node is not None and hasattr(node, "check_timers"):
                outbound = node.check_timers(now_us)
                self._route_outbound_messages(target_node_id, outbound, now_us)

                interval = (
                    getattr(node, "heartbeat_interval_us", 50000)
                    if getattr(node, "role", None) == RaftRole.LEADER
                    else getattr(node, "election_timeout_us", 150000)
                )
                next_tick = BaseEvent(
                    sequence_id=self.next_sequence_id(),
                    timestamp_us=now_us + interval,
                    priority=EventPriority.DIAGNOSTIC,
                    event_type="node.timer_tick",
                    target=target_node_id,
                    payload={},
                )
                self.schedule_event(next_tick)

        elif event.event_type == "network.message_delivery":
            target_node_id = str(event.target)
            source_node_id = str(event.source)
            msg_payload = event.payload
            message_type = msg_payload["message_type"]
            data = msg_payload["data"]

            node = self.nodes.get(target_node_id)
            if node is not None:
                outbound = node.handle_message(
                    sender=source_node_id,
                    message_type=message_type,
                    payload=data,
                    now_us=now_us,
                )
                self._route_outbound_messages(target_node_id, outbound, now_us)

    def _route_outbound_messages(
        self,
        sender: NodeId,
        outbound: Sequence[tuple[NodeId, str, dict[str, Any]]],
        now_us: VirtualMicroseconds,
    ) -> None:
        """Pass outbound messages through the simulated network to calculate latency or drops."""
        for target, msg_type, data in outbound:
            will_deliver, arrival_time_us, reason = self.network.calculate_delivery(
                source=sender,
                target=target,
                current_time_us=now_us,
                message_type=msg_type,
            )
            if will_deliver:
                delivery_event = MessageDeliveryEvent.create(
                    sequence_id=self.next_sequence_id(),
                    timestamp_us=arrival_time_us,
                    source=sender,
                    target=target,
                    message_type=msg_type,
                    data=data,
                )
                self.schedule_event(delivery_event)
