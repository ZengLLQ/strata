"""Integration test simulating a 3-node Raft consensus cluster with fault injection and linearizability check."""

from __future__ import annotations

from pathlib import Path
import pytest

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
from strata.core.types import NodeState, RunStatus
from strata.simulation.engine import DeterministicSimulationEngine


def test_raft_cluster_replication_and_linearizability(tmp_path: Path) -> None:
    """Execute end-to-end discrete-event simulation of a 3-node Raft cluster with linearizability validation."""
    exp = ExperimentDefinition(
        metadata=ExperimentMetadata(
            id="exp_raft_consensus_01",
            name="Three-Node Raft Consensus with Linearizability Verification",
        ),
        execution=ExecutionConfig(seed=42, deterministic=True),
        topology=TopologyConfig(
            nodes=[
                NodeConfig(id="node-1", role="raft_node", parameters={"election_timeout_us": 50000}),
                NodeConfig(id="node-2", role="raft_node", parameters={"election_timeout_us": 80000}),
                NodeConfig(id="node-3", role="raft_node", parameters={"election_timeout_us": 120000}),
            ],
            network=NetworkConfig(default_latency_us=2000),
        ),
        workload=WorkloadConfig(
            workload_type="raft_kv",
            operations_count=5,
            arrival_interval_us=40000,
            key_space_size=2,
            target_nodes=["node-1"],
        ),
        faults=[
            # Crash node-3 temporarily
            FaultConfig(
                id="crash_node_3",
                fault_type="node_crash",
                target="node-3",
                trigger_time_us=60000,
                duration_us=40000,
            )
        ],
        invariants=[
            InvariantConfig(id="inv_linearizable", invariant_type="linearizability"),
            InvariantConfig(id="inv_convergence", invariant_type="state_convergence"),
            InvariantConfig(id="inv_faults", invariant_type="fault_observed"),
            InvariantConfig(id="inv_panic", invariant_type="no_panic"),
        ],
        artifacts=ArtifactsConfig(output_dir=str(tmp_path), persist_sqlite=True),
    )

    engine = DeterministicSimulationEngine(experiment=exp)
    result = engine.run()

    assert result.status == RunStatus.COMPLETED
    assert result.events_processed > 0
    assert result.all_invariants_passed is True

    # Check linearizability invariant details
    lin_res = next(r for r in result.invariant_results if r.invariant_type == "linearizability")
    assert lin_res.verdict.value == "passed"
    assert "linearized_sequence" in lin_res.details
