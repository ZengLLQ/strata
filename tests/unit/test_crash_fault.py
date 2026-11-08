"""Unit tests for the node crash fault and recovery."""

import pytest
from strata.core.errors import FaultApplicationError
from strata.core.experiment import ExperimentDefinition
from strata.core.types import FaultPhase, NodeState
from strata.faults.crash import NodeCrashFault, NodeRestartFault
from strata.simulation.engine import DeterministicSimulationEngine


def test_node_crash_fault_application(sample_experiment_def: ExperimentDefinition) -> None:
    engine = DeterministicSimulationEngine(experiment=sample_experiment_def)
    target_node = engine.nodes["node-2"]
    assert target_node.state == NodeState.ONLINE

    fault = NodeCrashFault(
        fault_id="crash_test",
        target="node-2",
        trigger_time_us=5000,
        duration_us=10000,
    )

    evidence = fault.apply(engine, now_us=5000)

    assert fault.phase == FaultPhase.APPLIED
    assert target_node.state == NodeState.OFFLINE
    assert evidence["previous_state"] == NodeState.ONLINE.value
    assert evidence["new_state"] == NodeState.OFFLINE.value
    assert evidence["restart_scheduled_at_us"] == 15000

    # Verify that events were logged on the engine
    events = engine.event_history
    assert len(events) >= 2
    event_types = [e.event_type for e in events]
    assert "node.state_change" in event_types
    assert "fault.applied" in event_types


def test_node_crash_unknown_target(sample_experiment_def: ExperimentDefinition) -> None:
    engine = DeterministicSimulationEngine(experiment=sample_experiment_def)
    fault = NodeCrashFault(
        fault_id="crash_invalid",
        target="ghost-node",
        trigger_time_us=5000,
    )

    with pytest.raises(FaultApplicationError, match="ghost-node"):
        fault.apply(engine, now_us=5000)


def test_node_restart_fault_application(sample_experiment_def: ExperimentDefinition) -> None:
    engine = DeterministicSimulationEngine(experiment=sample_experiment_def)
    target_node = engine.nodes["node-2"]
    target_node.crash(1000)
    assert target_node.state == NodeState.OFFLINE

    restart_fault = NodeRestartFault(
        fault_id="restart_test",
        target="node-2",
        trigger_time_us=2000,
    )

    evidence = restart_fault.apply(engine, now_us=2000)
    assert restart_fault.phase == FaultPhase.APPLIED
    assert target_node.state == NodeState.ONLINE
    assert evidence["new_state"] == NodeState.ONLINE.value
