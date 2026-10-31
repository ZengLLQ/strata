"""Example demonstrating programmatic execution of an integration experiment with HttpServiceAdapter."""

from __future__ import annotations

from pathlib import Path
from rich import print as rprint

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
from strata.core.types import ExecutionMode
from strata.evidence.bundle import EvidenceBundle
from strata.storage.database import DatabaseManager
from strata.storage.repository import RunRepository


def main() -> None:
    # 1. Start an in-process 3-node HTTP test cluster
    rprint("[bold cyan]Starting in-process HTTP cluster (3 nodes)...[/]")
    cluster = TestHttpCluster(base_port=18300)
    endpoints = cluster.start()
    rprint(f"Cluster ready: {endpoints}")

    try:
        # 2. Programmatically construct an integration experiment definition
        experiment = ExperimentDefinition(
            metadata=ExperimentMetadata(
                id="exp_http_integ_demo",
                name="Programmatic HTTP Cluster Integration Experiment",
                description="Validating replicated KV and crash recovery across real HTTP nodes.",
            ),
            execution=ExecutionConfig(
                mode=ExecutionMode.INTEGRATION,
                seed=99,
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
                arrival_interval_us=10000,
                key_space_size=3,
                target_nodes=["node-1"],
            ),
            faults=[
                FaultConfig(
                    id="crash_node_2",
                    fault_type="node_crash",
                    target="node-2",
                    trigger_time_us=10000,
                    duration_us=20000,
                )
            ],
            invariants=[
                InvariantConfig(id="inv_fault_check", invariant_type="fault_observed"),
                InvariantConfig(id="inv_no_panic", invariant_type="no_panic"),
                InvariantConfig(id="inv_convergence", invariant_type="state_convergence"),
            ],
            artifacts=ArtifactsConfig(output_dir="./artifacts"),
        )

        rprint(f"[bold magenta]Starting integration execution for:[/] {experiment.metadata.name}")

        # 3. Create adapter and harness
        adapter = HttpServiceAdapter(endpoints=endpoints, allow_destructive=False)
        harness = IntegrationHarness(experiment=experiment, adapter=adapter)

        # 4. Execute integration run
        result = harness.run()

        rprint("[bold green]Integration Run Completed![/]")
        rprint(f"  Run ID: {result.run_id}")
        rprint(f"  Mode: {result.execution_mode.value.upper()}")
        rprint(f"  Events Recorded: {result.events_processed}")
        rprint(f"  Wall-Clock Duration: {result.wall_clock_duration_s:.4f} s")
        rprint(f"  All Invariants Passed: {result.all_invariants_passed}")

        # 5. Create evidence bundle
        bundle_dir = Path(experiment.artifacts.output_dir) / result.run_id
        EvidenceBundle.create_bundle(
            bundle_dir=bundle_dir,
            run_result=result,
            experiment_definition_raw=experiment.model_dump_json(indent=2),
        )
        rprint(f"  Evidence bundle stored at: {bundle_dir}")

        # 6. Save metadata to SQLite
        db_mgr = DatabaseManager(Path(experiment.artifacts.output_dir) / "strata_runs.db")
        repo = RunRepository(db_mgr)
        repo.save_run(result)
        rprint("  Run metadata saved to SQLite repository.")

    finally:
        # Tear down cluster
        rprint("[dim]Stopping HTTP test cluster...[/]")
        cluster.stop()
        rprint("[dim]Cluster stopped.[/]")


if __name__ == "__main__":
    main()
