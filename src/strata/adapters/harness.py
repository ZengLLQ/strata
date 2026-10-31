"""Integration Harness orchestrating real-system distributed testing."""

from __future__ import annotations

import time
from typing import Any, Callable, Sequence
import uuid

from strata.adapters.base import BaseServiceAdapter
from strata.adapters.http import HttpServiceAdapter
from strata.core.contracts import EventContract
from strata.core.errors import (
    ConfigurationError,
    HealthCheckFailedError,
    SimulationTimeoutError,
)
from strata.core.experiment import ExperimentDefinition, FaultConfig
from strata.core.types import ExecutionMode, NodeState, RunStatus
from strata.invariants.base import InvariantResult
from strata.invariants.registry import InvariantRegistry
from strata.simulation.engine import RunResult
from strata.simulation.events import BaseEvent, FaultAppliedEvent


class IntegrationNodeProxy:
    """Lightweight adapter exposing real node state snapshots to invariant evaluators."""

    def __init__(self, node_id: str, state: NodeState, state_snapshot: dict[str, Any]) -> None:
        self.node_id = node_id
        self.state = state
        self._snapshot = state_snapshot

    def get_state_snapshot(self) -> dict[str, Any]:
        return self._snapshot


class IntegrationHarness:
    """Orchestrator for testing real distributed systems and external services.
    
    Coordinates pre-flight environment setup, health probes, workload pacing,
    real-time fault orchestration, result collection, invariant evaluation,
    and safe teardown. Execution is explicitly non-deterministic and labeled
    as ExecutionMode.INTEGRATION.
    """

    def __init__(
        self,
        experiment: ExperimentDefinition,
        adapter: BaseServiceAdapter | None = None,
        run_id: str | None = None,
        event_callback: Callable[[BaseEvent], None] | None = None,
    ) -> None:
        if experiment.execution.mode != ExecutionMode.INTEGRATION:
            raise ConfigurationError(
                f"IntegrationHarness requires 'execution.mode == integration', got '{experiment.execution.mode.value}'"
            )

        self.experiment = experiment
        self.run_id = run_id or f"run_integ_{uuid.uuid4().hex[:10]}"
        self.event_callback = event_callback
        self.event_history: list[BaseEvent] = []
        self._sequence_counter = 0

        # Build or attach adapter
        if adapter is not None:
            self.adapter = adapter
        else:
            self.adapter = self._build_default_adapter(experiment)

        # Build invariant instances from registry
        self.invariants = [
            InvariantRegistry.create(inv.invariant_type, inv.id, inv.description, inv.parameters)
            for inv in experiment.invariants
        ]

        self.nodes: dict[str, IntegrationNodeProxy] = {}

    def _build_default_adapter(self, exp: ExperimentDefinition) -> BaseServiceAdapter:
        """Derive an HttpServiceAdapter from topology node configuration."""
        endpoints: dict[str, str] = {}
        for node in exp.topology.nodes:
            ep = node.parameters.get("endpoint") or node.parameters.get("url")
            if ep:
                endpoints[node.id] = str(ep)

        if not endpoints:
            raise ConfigurationError(
                "Cannot build default HTTP adapter: no 'endpoint' or 'url' found in node parameters."
            )

        return HttpServiceAdapter(
            endpoints=endpoints,
            allow_destructive=exp.execution.allow_destructive,
        )

    def _next_sequence_id(self) -> int:
        self._sequence_counter += 1
        return self._sequence_counter

    def _record_event(self, event: EventContract) -> None:
        if isinstance(event, BaseEvent):
            self.event_history.append(event)
            if self.event_callback:
                self.event_callback(event)

    def run(self) -> RunResult:
        """Execute the real-system integration experiment."""
        start_wall_clock = time.perf_counter()
        start_time_ns = time.time_ns()
        status = RunStatus.RUNNING
        env_meta = self.adapter.get_environment_metadata()
        limits = self.experiment.limits
        timeout_s = limits.wall_clock_timeout_seconds

        try:
            # 1. Environment Setup & Health Verification
            self.adapter.setup(timeout_seconds=min(timeout_s, 30.0))
            if not self.adapter.health_check(timeout_seconds=5.0):
                raise HealthCheckFailedError("External cluster failed pre-flight health check probe.")

            # 2. Schedule and execute faults alongside workload
            # Sort faults by trigger time
            pending_faults = sorted(self.experiment.faults, key=lambda f: f.trigger_time_us)
            active_recoveries: list[tuple[int, FaultConfig]] = []

            # Execute workload operations
            workload_events = self.adapter.execute_workload(self.experiment.workload, start_time_ns)
            for we in workload_events:
                self._record_event(we)

                # Check if elapsed time warrants fault application
                now_us = (time.time_ns() - start_time_ns) // 1000
                while pending_faults and now_us >= pending_faults[0].trigger_time_us:
                    fault = pending_faults.pop(0)
                    now_elapsed_ns = time.time_ns() - start_time_ns
                    fault_evt = self.adapter.inject_fault(fault, now_elapsed_ns)
                    self._record_event(fault_evt)

                    if fault.duration_us:
                        recovery_time_us = fault.trigger_time_us + fault.duration_us
                        recovery_fault_type = "node_restart" if fault.fault_type == "node_crash" else "network_heal"
                        recovery_config = FaultConfig(
                            id=f"heal_{fault.id}",
                            fault_type=recovery_fault_type,
                            target=fault.target,
                            trigger_time_us=recovery_time_us,
                            parameters=fault.parameters,
                        )
                        active_recoveries.append((recovery_time_us, recovery_config))

                # Check recovery faults
                now_us = (time.time_ns() - start_time_ns) // 1000
                due_recoveries = [r for r in active_recoveries if now_us >= r[0]]
                for rec_time, rec_fault in due_recoveries:
                    active_recoveries.remove((rec_time, rec_fault))
                    now_elapsed_ns = time.time_ns() - start_time_ns
                    rec_evt = self.adapter.inject_fault(rec_fault, now_elapsed_ns)
                    self._record_event(rec_evt)

                # Enforce wall clock timeout
                if time.perf_counter() - start_wall_clock > timeout_s:
                    raise SimulationTimeoutError(
                        f"Integration experiment exceeded wall-clock timeout of {timeout_s}s"
                    )

            # Fire remaining scheduled faults if workload finished early
            while pending_faults:
                fault = pending_faults.pop(0)
                now_elapsed_ns = time.time_ns() - start_time_ns
                fault_evt = self.adapter.inject_fault(fault, now_elapsed_ns)
                self._record_event(fault_evt)

            # Fire remaining recoveries
            while active_recoveries:
                _, rec_fault = active_recoveries.pop(0)
                now_elapsed_ns = time.time_ns() - start_time_ns
                rec_evt = self.adapter.inject_fault(rec_fault, now_elapsed_ns)
                self._record_event(rec_evt)

            status = RunStatus.COMPLETED

        except Exception as exc:
            status = RunStatus.FAILED
            raise exc

        finally:
            wall_duration = time.perf_counter() - start_wall_clock
            elapsed_us = int((time.time_ns() - start_time_ns) // 1000)

            # 3. Always Teardown external resources safely
            try:
                self.adapter.teardown()
            except Exception:
                pass

        # 4. Result Collection & Node State Capture
        results = self.adapter.collect_results()
        node_states = results.get("node_states", {})

        self.nodes = {
            node_id: IntegrationNodeProxy(
                node_id=node_id,
                state=NodeState.ONLINE,
                state_snapshot=node_states.get(node_id, {}),
            )
            for node_id in [n.id for n in self.experiment.topology.nodes]
        }

        # 5. Evaluate Invariants against the real event history
        invariant_results: list[InvariantResult] = []
        for inv in self.invariants:
            inv_res = inv.evaluate(self, self.event_history)
            invariant_results.append(inv_res)

        # 6. Compose Execution Metadata with determinism limits
        execution_metadata: dict[str, Any] = {
            "mode": ExecutionMode.INTEGRATION.value,
            "adapter": self.adapter.adapter_name,
            "environment": env_meta,
            "determinism_limitations": self.adapter.get_determinism_limitations(),
        }

        return RunResult(
            run_id=self.run_id,
            experiment_id=self.experiment.metadata.id,
            status=status,
            seed=self.experiment.execution.seed,
            events_processed=len(self.event_history),
            final_virtual_time_us=elapsed_us,
            wall_clock_duration_s=wall_duration,
            invariant_results=invariant_results,
            events=self.event_history,
            node_states=node_states,
            execution_mode=ExecutionMode.INTEGRATION,
            metadata=execution_metadata,
        )
