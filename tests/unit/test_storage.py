"""Unit tests for SQLite run metadata storage and artifact manifest verification."""

from pathlib import Path
import pytest

from strata.core.errors import ArtifactIntegrityError
from strata.core.types import InvariantVerdict, RunStatus
from strata.evidence.manifest import RunManifest, compute_sha256
from strata.invariants.base import InvariantResult
from strata.simulation.engine import RunResult
from strata.storage.database import DatabaseManager
from strata.storage.repository import RunRepository


def test_sqlite_repository_save_and_retrieve(tmp_dir: Path) -> None:
    db_path = tmp_dir / "test_strata.db"
    db_mgr = DatabaseManager(db_path)
    repo = RunRepository(db_mgr)

    inv_res = InvariantResult(
        invariant_id="inv_test",
        invariant_type="state_convergence",
        verdict=InvariantVerdict.PASSED,
        explanation="Test explanation",
        details={"key": "val"},
    )

    run_result = RunResult(
        run_id="run_12345",
        experiment_id="exp_test",
        status=RunStatus.COMPLETED,
        seed=42,
        events_processed=15,
        final_virtual_time_us=50000,
        wall_clock_duration_s=0.012,
        invariant_results=[inv_res],
        events=[],
    )

    # Save to SQLite
    repo.save_run(run_result, manifest_hash="sha256_dummy_hash")

    # Retrieve and verify
    record = repo.get_run("run_12345")
    assert record is not None
    assert record.run_id == "run_12345"
    assert record.experiment_id == "exp_test"
    assert record.status == "completed"
    assert record.seed == 42
    assert record.events_processed == 15
    assert record.all_invariants_passed == 1
    assert record.manifest_hash == "sha256_dummy_hash"
    assert len(record.invariant_records) == 1
    assert record.invariant_records[0].invariant_id == "inv_test"
    assert record.invariant_records[0].verdict == "passed"


def test_manifest_verification_and_tamper_detection(tmp_dir: Path) -> None:
    file_a = tmp_dir / "data.txt"
    file_a.write_text("authentic experiment payload", encoding="utf-8")

    manifest = RunManifest(
        run_id="run_integrity",
        experiment_id="exp_integrity",
        seed=1,
    )
    manifest.add_artifact("data.txt", file_a)

    manifest_file = tmp_dir / "manifest.json"
    manifest.write_to(manifest_file)

    # 1. Verification succeeds on untampered file
    loaded_manifest = RunManifest.load_from(manifest_file)
    results = loaded_manifest.verify_directory(tmp_dir)
    assert results["data.txt"] is True

    # 2. Tamper with file_a
    file_a.write_text("tampered corrupted payload", encoding="utf-8")
    with pytest.raises(ArtifactIntegrityError, match="Checksum mismatch"):
        loaded_manifest.verify_directory(tmp_dir)
