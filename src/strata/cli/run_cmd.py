"""Implementation of 'strata run' CLI command."""

from __future__ import annotations

from pathlib import Path
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from strata.adapters.harness import IntegrationHarness
from strata.core.errors import AdapterError, ConfigurationError, SimulationError
from strata.core.experiment import ExperimentDefinition
from strata.core.types import ExecutionMode
from strata.evidence.bundle import EvidenceBundle
from strata.evidence.event_log import JsonlEventLogger
from strata.simulation.engine import DeterministicSimulationEngine
from strata.storage.database import DatabaseManager
from strata.storage.repository import RunRepository

console = Console()


def run_command(
    path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to experiment specification YAML file",
    ),
    seed: int | None = typer.Option(
        None,
        "--seed",
        "-s",
        help="Override the random seed specified in experiment configuration",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Override directory where experiment artifacts and database will be written",
    ),
) -> None:
    """Execute an experiment under deterministic discrete-event simulation."""
    # 1. Load experiment
    try:
        raw_text = path.read_text(encoding="utf-8")
        exp = ExperimentDefinition.from_yaml(path)
    except ConfigurationError as err:
        console.print(f"[bold red]Configuration Error:[/] {err}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Error Loading Experiment:[/] {exc}")
        raise typer.Exit(code=1)

    # 2. Apply CLI overrides
    if seed is not None:
        exp = exp.model_copy(update={"execution": exp.execution.model_copy(update={"seed": seed})})
    if output_dir is not None:
        exp = exp.model_copy(update={"artifacts": exp.artifacts.model_copy(update={"output_dir": str(output_dir)})})

    target_artifacts_dir = Path(exp.artifacts.output_dir)
    target_artifacts_dir.mkdir(parents=True, exist_ok=True)

    # 3. Instantiate and run appropriate engine/harness
    if exp.execution.mode == ExecutionMode.INTEGRATION:
        console.print(
            f"[dim]Executing experiment:[/] [bold]{exp.metadata.name}[/] "
            "[bold magenta][INTEGRATION MODE — Real Services][/]"
        )
        harness = IntegrationHarness(experiment=exp)
        try:
            result = harness.run()
        except AdapterError as adapt_err:
            console.print(f"[bold red]Integration Adapter Failed:[/] {adapt_err}")
            raise typer.Exit(code=1)
        except Exception as exc:
            console.print(f"[bold red]Unexpected Integration Failure:[/] {exc}")
            raise typer.Exit(code=1)
    else:
        console.print(
            f"[dim]Executing experiment:[/] [bold]{exp.metadata.name}[/] "
            f"[bold cyan][SIMULATION MODE][/] [dim](seed={exp.execution.seed})[/]"
        )
        engine = DeterministicSimulationEngine(experiment=exp)
        try:
            result = engine.run()
        except SimulationError as sim_err:
            console.print(f"[bold red]Simulation Execution Failed:[/] {sim_err}")
            raise typer.Exit(code=1)
        except Exception as exc:
            console.print(f"[bold red]Unexpected Engine Failure:[/] {exc}")
            raise typer.Exit(code=1)

    # 4. Generate artifacts bundle
    run_bundle_dir = target_artifacts_dir / result.run_id
    EvidenceBundle.create_bundle(
        bundle_dir=run_bundle_dir,
        run_result=result,
        experiment_definition_raw=raw_text,
    )

    # 5. Persist metadata to SQLite
    if exp.artifacts.persist_sqlite:
        db_path = target_artifacts_dir / "strata_runs.db"
        db_mgr = DatabaseManager(db_path)
        repo = RunRepository(db_mgr)
        manifest_path = run_bundle_dir / "manifest.json"
        manifest_hash = None
        if manifest_path.exists():
            from strata.evidence.manifest import compute_sha256
            manifest_hash = compute_sha256(manifest_path)
        repo.save_run(result, manifest_hash=manifest_hash)

    # 6. Render technical execution summary
    status_style = "bold green" if result.status.value == "completed" else "bold red"
    if exp.execution.mode == ExecutionMode.INTEGRATION:
        panel_title = "Integration Run Summary"
        panel_border = "magenta"
        timing_line = f"Elapsed Wall-Clock: [bold]{result.wall_clock_duration_s:.4f}[/] s ({result.final_virtual_time_us:,} us)\n"
        mode_line = "Execution Mode: [bold magenta]INTEGRATION[/] (Real System / External Services)\nDeterminism: [dim]None (Real-system OS scheduling, network, GC)[/]\n"
    else:
        panel_title = "Simulation Summary"
        panel_border = "cyan"
        timing_line = f"Virtual Duration: [bold]{result.final_virtual_time_us:,}[/] us\nWall-Clock Time: [bold]{result.wall_clock_duration_s:.4f}[/] s\n"
        mode_line = "Execution Mode: [bold cyan]SIMULATION[/] (Deterministic Discrete-Event)\n"

    console.print(
        Panel.fit(
            f"Run ID: [bold]{result.run_id}[/]\n"
            f"{mode_line}"
            f"Status: [{status_style}]{result.status.value.upper()}[/]\n"
            f"{timing_line}"
            f"Events Dispatched: [bold]{result.events_processed:,}[/]\n"
            f"Artifacts Directory: [dim]{run_bundle_dir}[/]",
            title=panel_title,
            border_style=panel_border,
        )
    )

    # Invariants Table
    if result.invariant_results:
        inv_table = Table(title="Invariant Verdicts", border_style="dim")
        inv_table.add_column("Invariant ID", style="bold")
        inv_table.add_column("Type", style="cyan")
        inv_table.add_column("Verdict", justify="center")
        inv_table.add_column("Explanation")

        for inv in result.invariant_results:
            badge = "[bold green]PASSED[/]" if inv.verdict.value == "passed" else f"[bold red]{inv.verdict.value.upper()}[/]"
            inv_table.add_row(
                inv.invariant_id,
                inv.invariant_type,
                badge,
                inv.explanation,
            )
        console.print(inv_table)

    if not result.all_invariants_passed:
        console.print("\n[bold red]✗ One or more invariants were violated during this experiment.[/]")
        raise typer.Exit(code=1)

    console.print("\n[bold green]✓ Experiment simulation completed with all invariants passed.[/]")
