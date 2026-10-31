"""Integration test executing a complete network partition scenario."""

from pathlib import Path
from strata.core.experiment import ExperimentDefinition
from strata.core.types import RunStatus
from strata.evidence.bundle import EvidenceBundle
from strata.evidence.manifest import RunManifest
from strata.simulation.engine import DeterministicSimulationEngine
from strata.storage.database import DatabaseManager
from strata.storage.repository import RunRepository


def test_network_partition_experiment(tmp_dir: Path) -> None:
    example_path = Path("examples/network_partition.yaml")
    exp = ExperimentDefinition.from_yaml(example_path)

    # Point artifacts output to tmp_dir
    exp = exp.model_copy(
        update={"artifacts": exp.artifacts.model_copy(update={"output_dir": str(tmp_dir)})}
    )

    engine = DeterministicSimulationEngine(experiment=exp)
    result = engine.run()

    # 1. Assert status and invariants
    assert result.status == RunStatus.COMPLETED
    assert result.events_processed > 0
    assert result.all_invariants_passed is True

    verdicts = {inv.invariant_type: inv.verdict.value for inv in result.invariant_results}
    assert verdicts["partition_isolation"] == "passed"
    assert verdicts["fault_observed"] == "passed"
    assert verdicts["no_panic"] == "passed"

    # 2. Verify evidence bundle and manifest
    bundle_dir = tmp_dir / result.run_id
    EvidenceBundle.create_bundle(
        bundle_dir=bundle_dir,
        run_result=result,
        experiment_definition_raw=example_path.read_text(encoding="utf-8"),
    )

    manifest_file = bundle_dir / "manifest.json"
    assert manifest_file.exists()
    manifest = RunManifest.load_from(manifest_file)
    verification = manifest.verify_directory(bundle_dir)
    assert verification["events.jsonl"] is True

    # 3. Verify SQLite persistence
    db_mgr = DatabaseManager(tmp_dir / "strata_runs.db")
    repo = RunRepository(db_mgr)
    repo.save_run(result)

    retrieved = repo.get_run(result.run_id)
    assert retrieved is not None
    assert retrieved.experiment_id == "exp_network_partition_and_recovery"
    assert retrieved.all_invariants_passed == 1
    assert len(retrieved.invariant_records) == 3
