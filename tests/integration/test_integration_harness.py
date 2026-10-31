"""Integration test executing a complete real-system experiment using IntegrationHarness."""

from __future__ import annotations

from pathlib import Path
import pytest

from examples.http_test_server import TestHttpCluster
from strata.adapters.harness import IntegrationHarness
from strata.adapters.http import HttpServiceAdapter
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
from strata.core.types import ExecutionMode, RunStatus
from strata.evidence.bundle import EvidenceBundle
from strata.evidence.manifest import RunManifest
from strata.storage.database import DatabaseManager
from strata.storage.repository import RunRepository


@pytest.fixture(scope="module")
def live_http_cluster() -> TestHttpCluster:
    """Spin up an in-process 3-node HTTP cluster on ports 18201-18203."""
    cluster = TestHttpCluster(base_port=18200)
    cluster.start()
    yield cluster
    cluster.stop()


def test_integration_harness_end_to_end(
    live_http_cluster: TestHttpCluster,
    tmp_path: Path,
) -> None:
    endpoints = {
        "node-1": "http://127.0.0.1:18201",
        "node-2": "http://127.0.0.1:18202",
        "node-3": "http://127.0.0.1:18203",
    }

    # 1. Build an experiment definition with mode: integration
    exp = ExperimentDefinition(
        metadata=ExperimentMetadata(
            id="test_integ_01",
            name="End-to-End HTTP Cluster Integration Test",
            version="1.0.0",
        ),
        execution=ExecutionConfig(
            mode=ExecutionMode.INTEGRATION,
            seed=42,
            deterministic=False,
            allow_destructive=False,
        ),
        topology=TopologyConfig(
            nodes=[
                NodeConfig(id="node-1", role="coordinator", parameters={"endpoint": endpoints["node-1"]}),
                NodeConfig(id="node-2", role="replica", parameters={"endpoint": endpoints["node-2"]}),
                NodeConfig(id="node-3", role="replica", parameters={"endpoint": endpoints["node-3"]}),
            ],
            network=NetworkConfig(),
        ),
        workload=WorkloadConfig(
            workload_type="replicated_kv",
            operations_count=6,
            arrival_interval_us=5000,
            key_space_size=3,
            target_nodes=["node-1"],
        ),
        faults=[
            FaultConfig(
                id="crash_node_2",
                fault_type="node_crash",
                target="node-2",
                trigger_time_us=5000,
                duration_us=10000,
            )
        ],
        invariants=[
            InvariantConfig(id="inv_fault", invariant_type="fault_observed"),
            InvariantConfig(id="inv_panic", invariant_type="no_panic"),
            InvariantConfig(id="inv_convergence", invariant_type="state_convergence"),
        ],
        artifacts=ArtifactsConfig(output_dir=str(tmp_path)),
    )

    # 2. Instantiate and run IntegrationHarness
    adapter = HttpServiceAdapter(endpoints=endpoints, allow_destructive=False)
    harness = IntegrationHarness(experiment=exp, adapter=adapter)
    result = harness.run()

    # 3. Assert execution results and non-deterministic labeling
    assert result.status == RunStatus.COMPLETED
    assert result.execution_mode == ExecutionMode.INTEGRATION
    assert result.events_processed > 0
    assert result.wall_clock_duration_s > 0
    assert result.all_invariants_passed is True

    # 4. Check metadata captures environment and determinism limitations
    assert "environment" in result.metadata
    assert "determinism_limitations" in result.metadata
    assert "repeatability" in result.metadata["determinism_limitations"]

    # 5. Verify evidence bundle and cryptographic manifest
    bundle_dir = tmp_path / result.run_id
    EvidenceBundle.create_bundle(
        bundle_dir=bundle_dir,
        run_result=result,
        experiment_definition_raw=exp.model_dump_json(),
    )

    manifest_file = bundle_dir / "manifest.json"
    assert manifest_file.exists()

    manifest = RunManifest.load_from(manifest_file)
    verification = manifest.verify_directory(bundle_dir)
    assert verification["events.jsonl"] is True
    assert verification["experiment.yaml"] is True
    assert verification["run_summary.json"] is True

    # 6. Verify SQLite persistence
    db_path = tmp_path / "strata_runs.db"
    db_mgr = DatabaseManager(db_path)
    repo = RunRepository(db_mgr)
    saved_record = repo.save_run(result, manifest_hash="test_manifest_hash")
    assert saved_record.run_id == result.run_id

    fetched = repo.get_run(result.run_id)
    assert fetched is not None
    assert fetched.experiment_id == "test_integ_01"
    assert len(fetched.invariant_records) == 3
