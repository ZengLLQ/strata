"""Shared pytest fixtures for the Strata test suite."""

from __future__ import annotations

from pathlib import Path
import tempfile
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


@pytest.fixture
def tmp_dir() -> Path:
    """Provide a clean temporary directory for test artifacts."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def sample_experiment_def() -> ExperimentDefinition:
    """Standard 3-node cluster experiment definition fixture."""
    return ExperimentDefinition(
        metadata=ExperimentMetadata(
            id="test_exp_01",
            name="Test Three-Node Experiment",
            version="1.0.0",
        ),
        execution=ExecutionConfig(seed=42, deterministic=True),
        topology=TopologyConfig(
            nodes=[
                NodeConfig(id="node-1", role="coordinator"),
                NodeConfig(id="node-2", role="replica"),
                NodeConfig(id="node-3", role="replica"),
            ],
            network=NetworkConfig(default_latency_us=1000, default_jitter_us=0, default_drop_rate=0.0),
        ),
        workload=WorkloadConfig(
            workload_type="replicated_kv",
            operations_count=5,
            arrival_interval_us=5000,
            key_space_size=2,
            target_nodes=["node-1"],
        ),
        faults=[
            FaultConfig(
                id="crash_node_2",
                fault_type="node_crash",
                target="node-2",
                trigger_time_us=12000,
                duration_us=10000,
            )
        ],
        invariants=[
            InvariantConfig(id="inv_fault", invariant_type="fault_observed"),
            InvariantConfig(id="inv_panic", invariant_type="no_panic"),
        ],
        artifacts=ArtifactsConfig(output_dir="./test_artifacts"),
    )
