"""Unit tests for the 'strata inspect' CLI command."""

from pathlib import Path
import pytest
import typer
from typer.testing import CliRunner

from strata.cli.main import app
from strata.core.types import InvariantVerdict, RunStatus
from strata.evidence.bundle import EvidenceBundle
from strata.invariants.base import InvariantResult
from strata.simulation.engine import RunResult
from strata.simulation.events import BaseEvent
from strata.core.types import EventPriority
from strata.storage.database import DatabaseManager
from strata.storage.repository import RunRepository

runner = CliRunner()


def test_inspect_missing_database(tmp_dir: Path) -> None:
    result = runner.invoke(app, ["inspect", "non_existent_run", "--artifacts-dir", str(tmp_dir)])
    assert result.exit_code == 1
    assert "Database not found" in result.output


def test_inspect_missing_run_id(tmp_dir: Path) -> None:
    db_mgr = DatabaseManager(tmp_dir / "strata_runs.db")
    result = runner.invoke(app, ["inspect", "unknown_run", "--artifacts-dir", str(tmp_dir)])
    assert result.exit_code == 1
    assert "Run 'unknown_run' not found" in result.output


def test_inspect_successful_run(tmp_dir: Path) -> None:
    db_mgr = DatabaseManager(tmp_dir / "strata_runs.db")
    repo = RunRepository(db_mgr)

    event = BaseEvent(
        sequence_id=1,
        timestamp_us=1000,
        priority=EventPriority.SYSTEM_FAULT,
        event_type="fault.applied",
        source="fault_injector",
        target="node-2",
        payload={"fault_id": "f1", "fault_type": "node_crash"},
    )

    inv = InvariantResult(
        invariant_id="inv_test",
        invariant_type="fault_observed",
        verdict=InvariantVerdict.PASSED,
        explanation="All faults applied",
    )

    run_res = RunResult(
        run_id="run_inspect_test",
        experiment_id="exp_inspect",
        status=RunStatus.COMPLETED,
        seed=42,
        events_processed=1,
        final_virtual_time_us=1000,
        wall_clock_duration_s=0.005,
        invariant_results=[inv],
        events=[event],
    )

    repo.save_run(run_res)

    # Create bundle
    bundle_dir = tmp_dir / "run_inspect_test"
    EvidenceBundle.create_bundle(
        bundle_dir=bundle_dir,
        run_result=run_res,
        experiment_definition_raw="metadata:\n  id: exp_inspect\n",
    )

    # Run inspect command
    result = runner.invoke(app, ["inspect", "run_inspect_test", "--artifacts-dir", str(tmp_dir), "--events"])
    assert result.exit_code == 0
    assert "run_inspect_test" in result.output
    assert "exp_inspect" in result.output
    assert "PASSED" in result.output
    assert "Event Timeline" in result.output
    assert "fault.applied" in result.output
