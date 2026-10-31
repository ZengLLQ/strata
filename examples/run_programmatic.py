"""Example demonstrating programmatic construction and execution of a Strata experiment."""

from __future__ import annotations

from pathlib import Path
from rich import print as rprint

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
from strata.simulation.engine import DeterministicSimulationEngine
from strata.storage.database import DatabaseManager
from strata.storage.repository import RunRepository


def main() -> None:
    # 1. Programmatically construct experiment definition
    experiment = ExperimentDefinition(
        metadata=ExperimentMetadata(
            id="exp_programmatic_demo",
            name="Programmatic Three-Node Cluster Simulation",
            description="Programmatic example constructing a 3-node cluster and executing deterministic simulation.",
        ),
        execution=ExecutionConfig(seed=1337, deterministic=True),
        topology=TopologyConfig(
            nodes=[
                NodeConfig(id="node-1", role="coordinator"),
                NodeConfig(id="node-2", role="replica"),
                NodeConfig(id="node-3", role="replica"),
            ],
            network=NetworkConfig(default_latency_us=1500, default_jitter_us=0),
        ),
        workload=WorkloadConfig(
            workload_type="replicated_kv",
            operations_count=5,
            arrival_interval_us=8000,
            target_nodes=["node-1"],
        ),
        faults=[
            FaultConfig(
                id="crash_node_3",
                fault_type="node_crash",
                target="node-3",
                trigger_time_us=12000,
                duration_us=20000,
            )
        ],
        invariants=[
            InvariantConfig(id="inv_fault_check", invariant_type="fault_observed"),
            InvariantConfig(id="inv_no_panic", invariant_type="no_panic"),
        ],
        artifacts=ArtifactsConfig(output_dir="./artifacts"),
    )

    rprint(f"[bold cyan]Starting simulation for:[/] {experiment.metadata.name}")

    # 2. Run deterministic simulation
    engine = DeterministicSimulationEngine(experiment=experiment)
    result = engine.run()

    rprint(f"[bold green]Simulation Completed![/]")
    rprint(f"  Run ID: {result.run_id}")
    rprint(f"  Events Dispatched: {result.events_processed}")
    rprint(f"  Final Virtual Time: {result.final_virtual_time_us} us")
    rprint(f"  All Invariants Passed: {result.all_invariants_passed}")

    # 3. Create evidence bundle
    bundle_dir = Path(experiment.artifacts.output_dir) / result.run_id
    EvidenceBundle.create_bundle(
        bundle_dir=bundle_dir,
        run_result=result,
        experiment_definition_raw=experiment.model_dump_json(indent=2),
    )
    rprint(f"  Evidence bundle stored at: {bundle_dir}")

    # 4. Save metadata to SQLite
    db_mgr = DatabaseManager(Path(experiment.artifacts.output_dir) / "strata_runs.db")
    repo = RunRepository(db_mgr)
    repo.save_run(result)
    rprint(f"  Run metadata saved to SQLite repository.")


if __name__ == "__main__":
    main()
