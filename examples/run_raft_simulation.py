"""Programmatic example demonstrating Raft consensus simulation with linearizability checking."""

from __future__ import annotations

from pathlib import Path
from rich import print as rprint

from strata.core.experiment import ExperimentDefinition
from strata.evidence.bundle import EvidenceBundle
from strata.simulation.engine import DeterministicSimulationEngine
from strata.storage.database import DatabaseManager
from strata.storage.repository import RunRepository


def main() -> None:
    exp_path = Path("examples/raft_cluster.yaml")
    rprint(f"[bold cyan]Loading Raft consensus experiment:[/] {exp_path}")
    experiment = ExperimentDefinition.from_yaml(exp_path)

    rprint(f"[bold]Executing deterministic simulation:[/] {experiment.metadata.name}")

    engine = DeterministicSimulationEngine(experiment=experiment)
    result = engine.run()

    rprint("\n[bold green]Simulation Completed![/]")
    rprint(f"  Run ID: {result.run_id}")
    rprint(f"  Events Dispatched: {result.events_processed}")
    rprint(f"  Virtual Duration: {result.final_virtual_time_us} us")
    rprint(f"  Wall-Clock Duration: {result.wall_clock_duration_s:.4f} s")
    rprint(f"  All Invariants Passed: {result.all_invariants_passed}")

    # Inspect Invariant Results
    rprint("\n[bold]Invariant Verdicts:[/]")
    for inv in result.invariant_results:
        badge = "[bold green]PASSED[/]" if inv.verdict.value == "passed" else f"[bold red]{inv.verdict.value.upper()}[/]"
        rprint(f"  • {inv.invariant_id} ({inv.invariant_type}): {badge}")
        if inv.invariant_type == "linearizability" and inv.verdict.value == "passed":
            seq = inv.details.get("linearized_sequence", [])
            rprint(f"    Linearized Certificate Length: {len(seq)} operations")

    # Final Node States
    rprint(f"\n[bold]Final Replicated Node States:[/]")
    for node_id, state in result.node_states.items():
        rprint(f"  • {node_id}: {state}")

    # Persist bundle
    bundle_dir = Path(experiment.artifacts.output_dir) / result.run_id
    EvidenceBundle.create_bundle(
        bundle_dir=bundle_dir,
        run_result=result,
        experiment_definition_raw=experiment.model_dump_json(indent=2),
    )
    rprint(f"\n[dim]Artifact bundle generated at: {bundle_dir}[/]")

    # Persist SQLite
    db_mgr = DatabaseManager(Path(experiment.artifacts.output_dir) / "strata_runs.db")
    repo = RunRepository(db_mgr)
    repo.save_run(result)
    rprint("[dim]Run record saved to SQLite repository.[/]")


if __name__ == "__main__":
    main()
