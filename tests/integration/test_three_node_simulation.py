"""Integration test executing a complete three-node cluster simulation with node crash."""

from pathlib import Path
from strata.core.experiment import ExperimentDefinition
from strata.core.types import NodeState, RunStatus
from strata.evidence.bundle import EvidenceBundle
from strata.evidence.manifest import RunManifest
from strata.simulation.engine import DeterministicSimulationEngine


def test_three_node_cluster_crash_and_recovery(
    sample_experiment_def: ExperimentDefinition,
    tmp_dir: Path,
) -> None:
    # Set artifacts output to temporary directory
    exp = sample_experiment_def.model_copy(
        update={"artifacts": sample_experiment_def.artifacts.model_copy(update={"output_dir": str(tmp_dir)})}
    )

    engine = DeterministicSimulationEngine(experiment=exp)
    result = engine.run()

    # 1. Assert run status and events
    assert result.status == RunStatus.COMPLETED
    assert result.events_processed > 0
    assert result.final_virtual_time_us > 0
    assert result.all_invariants_passed is True

    # 2. Verify node-2 lifecycle during run
    node2 = engine.nodes["node-2"]
    assert node2.crashed_at_us == 12000
    assert node2.recovered_at_us == 22000
    assert node2.state == NodeState.ONLINE

    # 3. Verify event stream contains node state transitions and fault applied events
    event_types = [e.event_type for e in result.events]
    assert "fault.applied" in event_types
    assert "node.state_change" in event_types
    assert "network.message_delivery" in event_types
    assert "workload.operation" in event_types

    # 4. Generate evidence bundle and verify manifest
    bundle_dir = tmp_dir / result.run_id
    EvidenceBundle.create_bundle(
        bundle_dir=bundle_dir,
        run_result=result,
        experiment_definition_raw=exp.model_dump_json(),
    )

    manifest_file = bundle_dir / "manifest.json"
    assert manifest_file.exists()

    manifest = RunManifest.load_from(manifest_file)
    verification_results = manifest.verify_directory(bundle_dir)
    assert verification_results["events.jsonl"] is True
    assert verification_results["experiment.yaml"] is True
    assert verification_results["run_summary.json"] is True
