"""Integration test executing baseline and failure runs, verifying bundles, and comparing runs."""

import json
from pathlib import Path
from typer.testing import CliRunner

from strata.cli.main import app
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
from strata.evidence.bundle import EvidenceBundle
from strata.evidence.comparison import RunComparator
from strata.simulation.engine import DeterministicSimulationEngine
from strata.storage.database import DatabaseManager
from strata.storage.repository import RunRepository

runner = CliRunner()


def test_baseline_vs_failure_run_comparison_integration(tmp_dir: Path) -> None:
    db_path = tmp_dir / "strata_runs.db"
    db_mgr = DatabaseManager(db_path)
    repo = RunRepository(db_mgr)

    # 1. Baseline Experiment (Healthy cluster, all nodes converge)
    baseline_def = ExperimentDefinition(
        metadata=ExperimentMetadata(
            id="exp_baseline_healthy",
            name="Healthy Baseline Run",
            version="1.0.0",
        ),
        execution=ExecutionConfig(seed=100, deterministic=True),
        topology=TopologyConfig(
            nodes=[
                NodeConfig(id="node-1", role="coordinator"),
                NodeConfig(id="node-2", role="replica"),
                NodeConfig(id="node-3", role="replica"),
            ],
            network=NetworkConfig(default_latency_us=500),
        ),
        workload=WorkloadConfig(
            workload_type="replicated_kv",
            operations_count=4,
            arrival_interval_us=2000,
            key_space_size=2,
            target_nodes=["node-1"],
        ),
        faults=[],
        invariants=[
            InvariantConfig(id="inv_conv", invariant_type="state_convergence"),
            InvariantConfig(id="inv_panic", invariant_type="no_panic"),
        ],
        artifacts=ArtifactsConfig(output_dir=str(tmp_dir)),
    )

    engine_baseline = DeterministicSimulationEngine(experiment=baseline_def, run_id="run_baseline_01")
    result_baseline = engine_baseline.run()

    assert result_baseline.all_invariants_passed is True
    repo.save_run(result_baseline)
    EvidenceBundle.create_bundle(
        bundle_dir=tmp_dir / result_baseline.run_id,
        run_result=result_baseline,
        experiment_definition_raw="metadata:\n  id: exp_baseline_healthy\n",
    )

    # 2. Failure Experiment (Permanent node crash, causing state divergence)
    failure_def = ExperimentDefinition(
        metadata=ExperimentMetadata(
            id="exp_failure_crashed",
            name="Fault-Injected Failure Run",
            version="1.0.0",
        ),
        execution=ExecutionConfig(seed=100, deterministic=True),
        topology=TopologyConfig(
            nodes=[
                NodeConfig(id="node-1", role="coordinator"),
                NodeConfig(id="node-2", role="replica"),
                NodeConfig(id="node-3", role="replica"),
            ],
            network=NetworkConfig(default_latency_us=500),
        ),
        workload=WorkloadConfig(
            workload_type="replicated_kv",
            operations_count=4,
            arrival_interval_us=2000,
            key_space_size=2,
            target_nodes=["node-1"],
        ),
        faults=[
            FaultConfig(
                id="crash_node_2_early",
                fault_type="node_crash",
                target="node-2",
                trigger_time_us=500,
                duration_us=None,  # Remains offline
            )
        ],
        invariants=[
            InvariantConfig(id="inv_conv", invariant_type="state_convergence"),
            InvariantConfig(id="inv_fault", invariant_type="fault_observed"),
            InvariantConfig(id="inv_panic", invariant_type="no_panic"),
        ],
        artifacts=ArtifactsConfig(output_dir=str(tmp_dir)),
    )

    engine_failure = DeterministicSimulationEngine(experiment=failure_def, run_id="run_failure_02")
    result_failure = engine_failure.run()

    repo.save_run(result_failure)
    EvidenceBundle.create_bundle(
        bundle_dir=tmp_dir / result_failure.run_id,
        run_result=result_failure,
        experiment_definition_raw="metadata:\n  id: exp_failure_crashed\n",
    )

    # 3. Test standalone 'strata verify' for both bundles
    verify_base = runner.invoke(app, ["verify", "run_baseline_01", "--artifacts-dir", str(tmp_dir)])
    assert verify_base.exit_code == 0
    assert "Artifact Bundle Verified" in verify_base.output
    assert "events.jsonl" in verify_base.output

    verify_fail = runner.invoke(app, ["verify", "run_failure_02", "--artifacts-dir", str(tmp_dir)])
    assert verify_fail.exit_code == 0
    assert "Artifact Bundle Verified" in verify_fail.output
    assert "run_summary.json" in verify_fail.output

    # 4. Test 'strata compare' CLI between baseline and failure runs
    compare_res = runner.invoke(
        app,
        ["compare", "run_baseline_01", "run_failure_02", "--artifacts-dir", str(tmp_dir)],
    )
    assert compare_res.exit_code == 0
    assert "Differential Run Comparison" in compare_res.output
    assert "run_baseline_01" in compare_res.output
    assert "run_failure_02" in compare_res.output
    assert "Execution Metrics Comparison" in compare_res.output
    assert "Invariant Verdicts Comparison" in compare_res.output
    assert "REGRESSION" in compare_res.output
    assert "ADDED" in compare_res.output

    # 5. Verify Programmatic RunComparator API
    rec_a = repo.get_run("run_baseline_01")
    rec_b = repo.get_run("run_failure_02")
    assert rec_a is not None and rec_b is not None

    comparison = RunComparator.compare_records(rec_a, rec_b, artifacts_dir=tmp_dir)
    assert comparison.metrics.run_a_id == "run_baseline_01"
    assert comparison.metrics.run_b_id == "run_failure_02"
    assert comparison.metrics.all_invariants_passed_a is True
    assert comparison.has_regressions is True
    assert comparison.has_invariant_divergence is True

    inv_map = {inv.invariant_id: inv for inv in comparison.invariants}
    assert inv_map["inv_conv"].delta_status == "REGRESSION"
    assert inv_map["inv_fault"].delta_status == "ADDED"
    assert inv_map["inv_panic"].delta_status == "UNCHANGED"

    # At least node-2 was crashed, so its key state differs or missing
    as_dict = comparison.to_dict()
    assert "metrics" in as_dict
    assert "invariants" in as_dict
    assert "node_diffs" in as_dict
