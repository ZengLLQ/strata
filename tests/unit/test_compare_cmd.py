"""Unit tests for the 'strata compare' CLI command and differential run analysis."""

import json
from pathlib import Path
import pytest
from typer.testing import CliRunner

from strata.cli.main import app
from strata.core.types import InvariantVerdict, RunStatus
from strata.evidence.bundle import EvidenceBundle
from strata.evidence.comparison import (
    InvariantDiff,
    MetricsDelta,
    NodeKeyDiff,
    NodeStateDiff,
    RunComparator,
    RunComparison,
)
from strata.invariants.base import InvariantResult
from strata.simulation.engine import RunResult
from strata.storage.database import DatabaseManager
from strata.storage.models import InvariantRecord, RunRecord
from strata.storage.repository import RunRepository

runner = CliRunner()


def test_compare_missing_database(tmp_dir: Path) -> None:
    result = runner.invoke(app, ["compare", "run_a", "run_b", "--artifacts-dir", str(tmp_dir)])
    assert result.exit_code == 1
    assert "Database not found" in result.output


def test_compare_missing_run_a(tmp_dir: Path) -> None:
    db_mgr = DatabaseManager(tmp_dir / "strata_runs.db")
    result = runner.invoke(app, ["compare", "missing_a", "some_b", "--artifacts-dir", str(tmp_dir)])
    assert result.exit_code == 1
    assert "Run A 'missing_a' not found" in result.output


def test_compare_missing_run_b(tmp_dir: Path) -> None:
    db_mgr = DatabaseManager(tmp_dir / "strata_runs.db")
    repo = RunRepository(db_mgr)

    run_a = RunResult(
        run_id="run_present_a",
        experiment_id="exp_a",
        status=RunStatus.COMPLETED,
        seed=42,
        events_processed=10,
        final_virtual_time_us=10000,
        wall_clock_duration_s=0.01,
        invariant_results=[],
        events=[],
    )
    repo.save_run(run_a)

    result = runner.invoke(app, ["compare", "run_present_a", "missing_b", "--artifacts-dir", str(tmp_dir)])
    assert result.exit_code == 1
    assert "Run B 'missing_b' not found" in result.output


def test_run_comparator_diff_metrics() -> None:
    rec_a = RunRecord(
        run_id="run_a",
        experiment_id="exp_1",
        status="completed",
        seed=42,
        events_processed=100,
        final_virtual_time_us=50_000,
        wall_clock_duration_s=0.100,
        all_invariants_passed=1,
        summary_json="{}",
    )
    rec_b = RunRecord(
        run_id="run_b",
        experiment_id="exp_1",
        status="completed",
        seed=42,
        events_processed=125,
        final_virtual_time_us=75_000,
        wall_clock_duration_s=0.150,
        all_invariants_passed=0,
        summary_json="{}",
    )

    metrics = RunComparator.diff_metrics(rec_a, rec_b)
    assert metrics.status_match is True
    assert metrics.seed_match is True
    assert metrics.virtual_time_delta_us == 25_000
    assert metrics.events_delta == 25
    assert abs(metrics.wall_clock_delta_s - 0.050) < 1e-5
    assert metrics.all_invariants_passed_a is True
    assert metrics.all_invariants_passed_b is False
    assert metrics.invariants_verdict_match is False


def test_run_comparator_diff_invariants() -> None:
    rec_a = RunRecord(
        run_id="run_a",
        experiment_id="exp_1",
        status="completed",
        seed=42,
        events_processed=10,
        final_virtual_time_us=1000,
        wall_clock_duration_s=0.01,
        all_invariants_passed=1,
        summary_json="{}",
    )
    rec_b = RunRecord(
        run_id="run_b",
        experiment_id="exp_1",
        status="completed",
        seed=42,
        events_processed=10,
        final_virtual_time_us=1000,
        wall_clock_duration_s=0.01,
        all_invariants_passed=0,
        summary_json="{}",
    )

    inv_same_a = InvariantRecord(
        run_id="run_a",
        invariant_id="inv_same",
        invariant_type="no_panic",
        verdict="passed",
        explanation="ok",
        details_json="{}",
    )
    inv_same_b = InvariantRecord(
        run_id="run_b",
        invariant_id="inv_same",
        invariant_type="no_panic",
        verdict="passed",
        explanation="ok",
        details_json="{}",
    )

    inv_regr_a = InvariantRecord(
        run_id="run_a",
        invariant_id="inv_conv",
        invariant_type="state_convergence",
        verdict="passed",
        explanation="all converged",
        details_json="{}",
    )
    inv_regr_b = InvariantRecord(
        run_id="run_b",
        invariant_id="inv_conv",
        invariant_type="state_convergence",
        verdict="violated",
        explanation="divergent",
        details_json="{}",
    )

    inv_added_b = InvariantRecord(
        run_id="run_b",
        invariant_id="inv_new",
        invariant_type="fault_observed",
        verdict="passed",
        explanation="fault applied",
        details_json="{}",
    )

    inv_removed_a = InvariantRecord(
        run_id="run_a",
        invariant_id="inv_old",
        invariant_type="no_panic",
        verdict="passed",
        explanation="clean",
        details_json="{}",
    )

    rec_a.invariant_records = [inv_same_a, inv_regr_a, inv_removed_a]
    rec_b.invariant_records = [inv_same_b, inv_regr_b, inv_added_b]

    diffs = RunComparator.diff_invariants(rec_a, rec_b)
    diff_map = {d.invariant_id: d for d in diffs}

    assert diff_map["inv_same"].is_match is True
    assert diff_map["inv_same"].delta_status == "UNCHANGED"

    assert diff_map["inv_conv"].is_match is False
    assert diff_map["inv_conv"].delta_status == "REGRESSION"

    assert diff_map["inv_new"].is_match is False
    assert diff_map["inv_new"].delta_status == "ADDED"

    assert diff_map["inv_old"].is_match is False
    assert diff_map["inv_old"].delta_status == "REMOVED"


def test_run_comparator_diff_node_states() -> None:
    states_a = {
        "node-1": {"key1": "val1", "key2": 10},
        "node-2": {"key1": "val1", "key2": 10},
    }
    states_b = {
        "node-1": {"key1": "val1", "key2": 20},  # MODIFIED key2
        "node-2": {"key1": "val1"},  # ONLY_IN_A key2
        "node-3": {"key3": "new"},  # ONLY_IN_B key3
    }

    node_diffs = RunComparator.diff_node_states(states_a, states_b)

    # node-1 check
    assert node_diffs["node-1"].is_identical is False
    assert len(node_diffs["node-1"].differences) == 1
    d1 = node_diffs["node-1"].differences[0]
    assert d1.key == "key2"
    assert d1.diff_type == "MODIFIED"
    assert d1.val_a == 10
    assert d1.val_b == 20

    # node-2 check
    assert node_diffs["node-2"].is_identical is False
    assert len(node_diffs["node-2"].differences) == 1
    d2 = node_diffs["node-2"].differences[0]
    assert d2.key == "key2"
    assert d2.diff_type == "ONLY_IN_A"

    # node-3 check
    assert node_diffs["node-3"].is_identical is False
    assert len(node_diffs["node-3"].differences) == 1
    d3 = node_diffs["node-3"].differences[0]
    assert d3.key == "key3"
    assert d3.diff_type == "ONLY_IN_B"


def test_compare_cli_identical_runs(tmp_dir: Path) -> None:
    db_mgr = DatabaseManager(tmp_dir / "strata_runs.db")
    repo = RunRepository(db_mgr)

    inv = InvariantResult(
        invariant_id="inv_conv",
        invariant_type="state_convergence",
        verdict=InvariantVerdict.PASSED,
        explanation="converged",
    )
    run_res = RunResult(
        run_id="run_baseline",
        experiment_id="exp_identical",
        status=RunStatus.COMPLETED,
        seed=42,
        events_processed=20,
        final_virtual_time_us=30_000,
        wall_clock_duration_s=0.02,
        invariant_results=[inv],
        events=[],
        node_states={"node-1": {"k": "v"}, "node-2": {"k": "v"}},
    )
    repo.save_run(run_res)

    # Compare run against itself
    result = runner.invoke(app, ["compare", "run_baseline", "run_baseline", "--artifacts-dir", str(tmp_dir)])
    assert result.exit_code == 0
    assert "Differential Run Comparison" in result.output
    assert "MATCH" in result.output
    assert "UNCHANGED" in result.output
    assert "All replica states are identical between both runs" in result.output


def test_compare_cli_divergent_runs(tmp_dir: Path) -> None:
    db_mgr = DatabaseManager(tmp_dir / "strata_runs.db")
    repo = RunRepository(db_mgr)

    inv_pass = InvariantResult(
        invariant_id="inv_conv",
        invariant_type="state_convergence",
        verdict=InvariantVerdict.PASSED,
        explanation="converged",
    )
    run_base = RunResult(
        run_id="run_base_1",
        experiment_id="exp_divergent",
        status=RunStatus.COMPLETED,
        seed=42,
        events_processed=20,
        final_virtual_time_us=30_000,
        wall_clock_duration_s=0.02,
        invariant_results=[inv_pass],
        events=[],
        node_states={"node-1": {"item": "apple"}, "node-2": {"item": "apple"}},
    )
    repo.save_run(run_base)

    inv_fail = InvariantResult(
        invariant_id="inv_conv",
        invariant_type="state_convergence",
        verdict=InvariantVerdict.VIOLATED,
        explanation="divergent keys detected",
    )
    run_fault = RunResult(
        run_id="run_fault_2",
        experiment_id="exp_divergent",
        status=RunStatus.COMPLETED,
        seed=42,
        events_processed=28,
        final_virtual_time_us=45_000,
        wall_clock_duration_s=0.035,
        invariant_results=[inv_fail],
        events=[],
        node_states={"node-1": {"item": "apple"}, "node-2": {"item": "banana"}},
    )
    repo.save_run(run_fault)

    result = runner.invoke(app, ["compare", "run_base_1", "run_fault_2", "--artifacts-dir", str(tmp_dir)])
    assert result.exit_code == 0
    assert "Differential Run Comparison" in result.output
    assert "REGRESSION" in result.output
    assert "+15,000 us" in result.output
    assert "+8" in result.output
    assert "Node State Differences" in result.output
    assert "MODIFIED" in result.output
    assert '"banana"' in result.output


def test_compare_cli_with_paths_and_db_file(tmp_dir: Path) -> None:
    db_path = tmp_dir / "strata_runs.db"
    db_mgr = DatabaseManager(db_path)
    repo = RunRepository(db_mgr)

    run_1 = RunResult(
        run_id="run_path_1",
        experiment_id="exp_paths",
        status=RunStatus.COMPLETED,
        seed=1,
        events_processed=10,
        final_virtual_time_us=10_000,
        wall_clock_duration_s=0.01,
        invariant_results=[],
        events=[],
    )
    repo.save_run(run_1)

    # Pass relative-style path to run_id and direct path to db file
    result = runner.invoke(app, ["compare", f"artifacts/{run_1.run_id}", run_1.run_id, "--artifacts-dir", str(db_path)])
    assert result.exit_code == 0
    assert "Differential Run Comparison" in result.output
    assert "MATCH" in result.output


def test_compare_cli_no_node_states(tmp_dir: Path) -> None:
    db_mgr = DatabaseManager(tmp_dir / "strata_runs.db")
    repo = RunRepository(db_mgr)

    run_no_nodes = RunResult(
        run_id="run_empty_nodes",
        experiment_id="exp_empty",
        status=RunStatus.COMPLETED,
        seed=1,
        events_processed=5,
        final_virtual_time_us=5000,
        wall_clock_duration_s=0.005,
        invariant_results=[],
        events=[],
        node_states={},
    )
    repo.save_run(run_no_nodes)

    result = runner.invoke(app, ["compare", "run_empty_nodes", "run_empty_nodes", "--artifacts-dir", str(tmp_dir)])
    assert result.exit_code == 0
    assert "No node state snapshots recorded for comparison" in result.output
