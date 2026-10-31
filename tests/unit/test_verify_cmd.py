"""Unit tests for the 'strata verify' CLI command."""

import json
from pathlib import Path
from typer.testing import CliRunner

from strata.cli.main import app
from strata.core.types import InvariantVerdict, RunStatus
from strata.evidence.bundle import EvidenceBundle
from strata.evidence.manifest import RunManifest
from strata.invariants.base import InvariantResult
from strata.simulation.engine import RunResult

runner = CliRunner()


def test_verify_missing_bundle_directory(tmp_dir: Path) -> None:
    result = runner.invoke(app, ["verify", "non_existent_run", "--artifacts-dir", str(tmp_dir)])
    assert result.exit_code == 1
    assert "Artifact bundle directory not found" in result.output


def test_verify_missing_manifest_file(tmp_dir: Path) -> None:
    bundle_dir = tmp_dir / "run_no_manifest"
    bundle_dir.mkdir(parents=True)

    result = runner.invoke(app, ["verify", "run_no_manifest", "--artifacts-dir", str(tmp_dir)])
    assert result.exit_code == 1
    assert "Manifest file 'manifest.json' not found" in result.output


def test_verify_malformed_manifest_json(tmp_dir: Path) -> None:
    bundle_dir = tmp_dir / "run_bad_json"
    bundle_dir.mkdir(parents=True)
    manifest_file = bundle_dir / "manifest.json"
    manifest_file.write_text("{invalid json", encoding="utf-8")

    result = runner.invoke(app, ["verify", "run_bad_json", "--artifacts-dir", str(tmp_dir)])
    assert result.exit_code == 1
    assert "Failed to parse manifest" in result.output


def test_verify_missing_required_artifact_in_manifest(tmp_dir: Path) -> None:
    bundle_dir = tmp_dir / "run_missing_rec"
    bundle_dir.mkdir(parents=True)

    # Create empty files
    (bundle_dir / "events.jsonl").write_text("", encoding="utf-8")
    (bundle_dir / "experiment.yaml").write_text("", encoding="utf-8")
    # Manifest missing "run_summary.json"
    manifest = RunManifest(
        run_id="run_missing_rec",
        experiment_id="exp_test",
        seed=42,
    )
    manifest.add_artifact("events.jsonl", bundle_dir / "events.jsonl")
    manifest.add_artifact("experiment.yaml", bundle_dir / "experiment.yaml")
    manifest.write_to(bundle_dir / "manifest.json")

    result = runner.invoke(app, ["verify", "run_missing_rec", "--artifacts-dir", str(tmp_dir)])
    assert result.exit_code == 1
    assert "Required artifact 'run_summary.json' is not recorded in manifest.json" in result.output


def test_verify_missing_artifact_file_on_disk(tmp_dir: Path) -> None:
    bundle_dir = tmp_dir / "run_file_deleted"
    bundle_dir.mkdir(parents=True)

    # Create bundle files
    f_events = bundle_dir / "events.jsonl"
    f_exp = bundle_dir / "experiment.yaml"
    f_sum = bundle_dir / "run_summary.json"

    f_events.write_text("{\"seq\": 1}\n", encoding="utf-8")
    f_exp.write_text("metadata:\n  id: exp_test\n", encoding="utf-8")
    f_sum.write_text("{\"status\": \"completed\"}", encoding="utf-8")

    manifest = RunManifest(
        run_id="run_file_deleted",
        experiment_id="exp_test",
        seed=42,
    )
    manifest.add_artifact("events.jsonl", f_events)
    manifest.add_artifact("experiment.yaml", f_exp)
    manifest.add_artifact("run_summary.json", f_sum)
    manifest.write_to(bundle_dir / "manifest.json")

    # Delete one required file from disk
    f_events.unlink()

    result = runner.invoke(app, ["verify", "run_file_deleted", "--artifacts-dir", str(tmp_dir)])
    assert result.exit_code == 1
    assert "Required artifact file 'events.jsonl' is missing from disk" in result.output


def test_verify_tampered_artifact_file(tmp_dir: Path) -> None:
    inv = InvariantResult(
        invariant_id="inv_test",
        invariant_type="no_panic",
        verdict=InvariantVerdict.PASSED,
        explanation="clean run",
    )
    run_res = RunResult(
        run_id="run_tampered",
        experiment_id="exp_tampered",
        status=RunStatus.COMPLETED,
        seed=42,
        events_processed=10,
        final_virtual_time_us=50_000,
        wall_clock_duration_s=0.01,
        invariant_results=[inv],
        events=[],
    )

    bundle_dir = tmp_dir / "run_tampered"
    EvidenceBundle.create_bundle(
        bundle_dir=bundle_dir,
        run_result=run_res,
        experiment_definition_raw="metadata:\n  id: exp_tampered\n",
    )

    # Tamper with run_summary.json
    summary_path = bundle_dir / "run_summary.json"
    summary_path.write_text("{\"tampered\": true}", encoding="utf-8")

    result = runner.invoke(app, ["verify", "run_tampered", "--artifacts-dir", str(tmp_dir)])
    assert result.exit_code == 1
    assert "Verification Failed" in result.output
    assert "Checksum mismatch" in result.output


def test_verify_valid_bundle_success(tmp_dir: Path) -> None:
    inv = InvariantResult(
        invariant_id="inv_test",
        invariant_type="no_panic",
        verdict=InvariantVerdict.PASSED,
        explanation="clean run",
    )
    run_res = RunResult(
        run_id="run_valid_bundle",
        experiment_id="exp_valid",
        status=RunStatus.COMPLETED,
        seed=42,
        events_processed=10,
        final_virtual_time_us=50_000,
        wall_clock_duration_s=0.01,
        invariant_results=[inv],
        events=[],
    )

    bundle_dir = tmp_dir / "run_valid_bundle"
    EvidenceBundle.create_bundle(
        bundle_dir=bundle_dir,
        run_result=run_res,
        experiment_definition_raw="metadata:\n  id: exp_valid\n",
    )

    result = runner.invoke(app, ["verify", "run_valid_bundle", "--artifacts-dir", str(tmp_dir)])
    assert result.exit_code == 0
    assert "Artifact Verification — run_valid_bundle" in result.output
    assert "experiment.yaml" in result.output
    assert "events.jsonl" in result.output
    assert "run_summary.json" in result.output
    assert "VERIFIED" in result.output
    assert "All 3 artifacts intact" in result.output


def test_verify_using_full_directory_path(tmp_dir: Path) -> None:
    inv = InvariantResult(
        invariant_id="inv_test",
        invariant_type="no_panic",
        verdict=InvariantVerdict.PASSED,
        explanation="clean run",
    )
    run_res = RunResult(
        run_id="run_path_arg",
        experiment_id="exp_path",
        status=RunStatus.COMPLETED,
        seed=42,
        events_processed=5,
        final_virtual_time_us=10_000,
        wall_clock_duration_s=0.01,
        invariant_results=[inv],
        events=[],
    )
    bundle_dir = tmp_dir / "run_path_arg"
    EvidenceBundle.create_bundle(
        bundle_dir=bundle_dir,
        run_result=run_res,
        experiment_definition_raw="metadata:\n  id: exp_path\n",
    )

    # Pass the full bundle_dir as the argument
    result = runner.invoke(app, ["verify", str(bundle_dir)])
    assert result.exit_code == 0
    assert "Artifact Verification — run_path_arg" in result.output
    assert "VERIFIED" in result.output


def test_verify_corrupted_events_jsonl(tmp_dir: Path) -> None:
    inv = InvariantResult(
        invariant_id="inv_test",
        invariant_type="no_panic",
        verdict=InvariantVerdict.PASSED,
        explanation="clean run",
    )
    run_res = RunResult(
        run_id="run_corrupt_events",
        experiment_id="exp_corrupt_events",
        status=RunStatus.COMPLETED,
        seed=42,
        events_processed=5,
        final_virtual_time_us=10_000,
        wall_clock_duration_s=0.01,
        invariant_results=[inv],
        events=[],
    )
    bundle_dir = tmp_dir / "run_corrupt_events"
    EvidenceBundle.create_bundle(
        bundle_dir=bundle_dir,
        run_result=run_res,
        experiment_definition_raw="metadata:\n  id: exp_corrupt_events\n",
    )

    # Corrupt events.jsonl
    events_path = bundle_dir / "events.jsonl"
    events_path.write_text("{\"corrupted_event\": true}\n", encoding="utf-8")

    result = runner.invoke(app, ["verify", "run_corrupt_events", "--artifacts-dir", str(tmp_dir)])
    assert result.exit_code == 1
    assert "Verification Failed" in result.output
    assert "events.jsonl" in result.output
