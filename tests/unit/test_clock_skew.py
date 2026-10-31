"""Unit tests for the clock skew fault injection and simulated node time perception."""

import pytest

from strata.core.errors import FaultApplicationError
from strata.core.experiment import (
    ArtifactsConfig,
    ExecutionConfig,
    ExperimentDefinition,
    ExperimentMetadata,
    FaultConfig,
    InvariantConfig,
    NetworkConfig,
    NodeConfig,
    TopologyConfig,
    WorkloadConfig,
)
from strata.core.types import FaultPhase
from strata.faults.clock import ClockSkewFault, ClockSkewResetFault
from strata.faults.registry import FaultRegistry
from strata.simulation.engine import DeterministicSimulationEngine
from strata.simulation.node import BaseSimulatedNode


def test_node_clock_offset_methods() -> None:
    node = BaseSimulatedNode(node_id="node-1")
    assert node.clock_offset_us == 0
    assert node.get_perceived_time(10_000) == 10_000

    # Positive skew
    node.set_clock_offset(2_500)
    assert node.clock_offset_us == 2_500
    assert node.get_perceived_time(10_000) == 12_500

    # Negative skew
    node.set_clock_offset(-3_000)
    assert node.clock_offset_us == -3_000
    assert node.get_perceived_time(10_000) == 7_000

    # Floor at 0
    node.set_clock_offset(-15_000)
    assert node.get_perceived_time(10_000) == 0

    # Reset
    node.reset_clock_offset()
    assert node.clock_offset_us == 0
    assert node.get_perceived_time(10_000) == 10_000


def test_clock_skew_fault_application(sample_experiment_def: ExperimentDefinition) -> None:
    engine = DeterministicSimulationEngine(experiment=sample_experiment_def)
    target_node = engine.nodes["node-2"]
    assert target_node.clock_offset_us == 0

    fault = ClockSkewFault(
        fault_id="skew_node_2",
        target="node-2",
        trigger_time_us=5000,
        offset_us=1500,
        duration_us=10000,
    )

    evidence = fault.apply(engine, now_us=5000)

    assert fault.phase == FaultPhase.APPLIED
    assert target_node.clock_offset_us == 1500
    assert evidence["previous_offset_us"] == 0
    assert evidence["new_offset_us"] == 1500
    assert evidence["perceived_time_us"] == 6500
    assert evidence["reset_scheduled_at_us"] == 15000

    # Check fault event was recorded in history
    applied_events = [e for e in engine.event_history if e.event_type == "fault.applied"]
    assert len(applied_events) == 1
    assert applied_events[0].payload["fault_id"] == "skew_node_2"


def test_clock_skew_reset_fault(sample_experiment_def: ExperimentDefinition) -> None:
    engine = DeterministicSimulationEngine(experiment=sample_experiment_def)
    target_node = engine.nodes["node-2"]
    target_node.set_clock_offset(4000)
    assert target_node.clock_offset_us == 4000

    reset_fault = ClockSkewResetFault(
        fault_id="reset_node_2",
        target="node-2",
        trigger_time_us=9000,
    )

    evidence = reset_fault.apply(engine, now_us=9000)
    assert reset_fault.phase == FaultPhase.APPLIED
    assert target_node.clock_offset_us == 0
    assert evidence["previous_offset_us"] == 4000
    assert evidence["new_offset_us"] == 0
    assert evidence["perceived_time_us"] == 9000


def test_clock_skew_unknown_target(sample_experiment_def: ExperimentDefinition) -> None:
    engine = DeterministicSimulationEngine(experiment=sample_experiment_def)
    fault = ClockSkewFault(
        fault_id="skew_unknown",
        target="ghost-node",
        trigger_time_us=1000,
        offset_us=500,
    )

    with pytest.raises(FaultApplicationError, match="ghost-node"):
        fault.apply(engine, now_us=1000)


def test_clock_skew_reset_unknown_target(sample_experiment_def: ExperimentDefinition) -> None:
    engine = DeterministicSimulationEngine(experiment=sample_experiment_def)
    reset_fault = ClockSkewResetFault(
        fault_id="reset_unknown",
        target="ghost-node",
        trigger_time_us=1000,
    )

    with pytest.raises(FaultApplicationError, match="ghost-node"):
        reset_fault.apply(engine, now_us=1000)


def test_fault_registry_clock_skew() -> None:
    cfg = FaultConfig(
        id="f_skew",
        fault_type="clock_skew",
        target="node-1",
        trigger_time_us=2000,
        parameters={"offset_us": 3500},
    )
    fault = FaultRegistry.create_from_config(cfg)
    assert isinstance(fault, ClockSkewFault)
    assert fault.offset_us == 3500
    assert fault.target == "node-1"

    # Test alternative "skew_us" parameter alias
    cfg_alias = FaultConfig(
        id="f_skew_alt",
        fault_type="clock_skew",
        target="node-1",
        trigger_time_us=2000,
        parameters={"skew_us": -1500},
    )
    fault_alt = FaultRegistry.create_from_config(cfg_alias)
    assert isinstance(fault_alt, ClockSkewFault)
    assert fault_alt.offset_us == -1500


def test_experiment_schema_validation_clock_skew() -> None:
    # Valid config
    valid_exp = ExperimentDefinition(
        metadata=ExperimentMetadata(id="exp_skew", name="Skew Test"),
        execution=ExecutionConfig(seed=1),
        topology=TopologyConfig(
            nodes=[NodeConfig(id="node-1")],
            network=NetworkConfig(),
        ),
        workload=WorkloadConfig(operations_count=1, target_nodes=["node-1"]),
        faults=[
            FaultConfig(
                id="skew_1",
                fault_type="clock_skew",
                target="node-1",
                trigger_time_us=1000,
                parameters={"offset_us": 500},
            )
        ],
    )
    assert len(valid_exp.faults) == 1

    # Invalid target
    with pytest.raises(ValueError, match="unknown node 'node-99'"):
        ExperimentDefinition(
            metadata=ExperimentMetadata(id="exp_bad", name="Bad"),
            topology=TopologyConfig(nodes=[NodeConfig(id="node-1")]),
            faults=[
                FaultConfig(
                    id="skew_bad_target",
                    fault_type="clock_skew",
                    target="node-99",
                    trigger_time_us=1000,
                    parameters={"offset_us": 500},
                )
            ],
        )

    # Missing offset_us / skew_us
    with pytest.raises(ValueError, match="requires integer 'offset_us'"):
        ExperimentDefinition(
            metadata=ExperimentMetadata(id="exp_bad", name="Bad"),
            topology=TopologyConfig(nodes=[NodeConfig(id="node-1")]),
            faults=[
                FaultConfig(
                    id="skew_no_offset",
                    fault_type="clock_skew",
                    target="node-1",
                    trigger_time_us=1000,
                    parameters={},
                )
            ],
        )


def test_simulation_run_with_clock_skew_and_duration() -> None:
    exp = ExperimentDefinition(
        metadata=ExperimentMetadata(id="exp_skew_sim", name="Simulation Skew"),
        execution=ExecutionConfig(seed=42),
        topology=TopologyConfig(
            nodes=[
                NodeConfig(id="node-1", role="coordinator"),
                NodeConfig(id="node-2", role="replica"),
            ],
            network=NetworkConfig(),
        ),
        workload=WorkloadConfig(operations_count=3, target_nodes=["node-1"]),
        faults=[
            FaultConfig(
                id="skew_node_2",
                fault_type="clock_skew",
                target="node-2",
                trigger_time_us=2000,
                duration_us=5000,  # Resets at t=7000us
                parameters={"offset_us": 10_000},
            )
        ],
        invariants=[
            InvariantConfig(id="inv_fault", invariant_type="fault_observed"),
            InvariantConfig(id="inv_panic", invariant_type="no_panic"),
        ],
        artifacts=ArtifactsConfig(),
    )

    engine = DeterministicSimulationEngine(experiment=exp)
    result = engine.run()

    assert result.status.value == "completed"
    assert result.all_invariants_passed is True

    # At completion (well after 7000us), the reset fault should have restored offset to 0
    assert engine.nodes["node-2"].clock_offset_us == 0
    # Both skew and skew_reset should have applied
    fault_events = [e for e in result.events if e.event_type == "fault.applied"]
    fault_ids = {e.payload.get("fault_id") for e in fault_events}
    assert "skew_node_2" in fault_ids
    assert "skew_node_2_reset" in fault_ids


def test_node_clock_drift() -> None:
    node = BaseSimulatedNode(node_id="node-drift")
    assert node.clock_drift_ppm == 0.0

    # Set drift of +50,000 ppm (5% fast) starting at t=1,000,000 us (1 second)
    node.set_clock_drift(drift_ppm=50_000, now_us=1_000_000)
    assert node.clock_drift_ppm == 50_000

    # At start time, perceived time equals actual time
    assert node.get_perceived_time(1_000_000) == 1_000_000

    # After 1 second (t=2,000,000), elapsed is 1,000,000 us
    # drift_us = 1_000_000 * (50_000 / 1_000_000) = 50_000 us
    # perceived = 2_000_000 + 50_000 = 2_050_000 us
    assert node.get_perceived_time(2_000_000) == 2_050_000

    # Test reset
    node.reset_clock_offset()
    assert node.clock_drift_ppm == 0.0
    assert node.get_perceived_time(2_000_000) == 2_000_000


def test_clock_skew_drift_fault_application(sample_experiment_def: ExperimentDefinition) -> None:
    engine = DeterministicSimulationEngine(experiment=sample_experiment_def)
    target_node = engine.nodes["node-1"]

    fault = ClockSkewFault(
        fault_id="skew_drift_1",
        target="node-1",
        trigger_time_us=5000,
        offset_us=1000,
        drift_ppm=200_000,  # 20% fast
    )
    evidence = fault.apply(engine, now_us=5000)

    assert target_node.clock_offset_us == 1000
    assert target_node.clock_drift_ppm == 200_000
    assert evidence["new_offset_us"] == 1000
    assert evidence["new_drift_ppm"] == 200_000
    assert evidence["reset_scheduled_at_us"] is None


def test_clock_skew_schema_rejection_boolean() -> None:
    # Booleans are subclasses of int in Python, must be rejected
    with pytest.raises(ValueError, match="requires integer 'offset_us'"):
        ExperimentDefinition(
            metadata=ExperimentMetadata(id="exp_bool_skew", name="Bool Skew"),
            topology=TopologyConfig(nodes=[NodeConfig(id="node-1")]),
            faults=[
                FaultConfig(
                    id="skew_bool",
                    fault_type="clock_skew",
                    target="node-1",
                    trigger_time_us=1000,
                    parameters={"offset_us": True},
                )
            ],
        )
