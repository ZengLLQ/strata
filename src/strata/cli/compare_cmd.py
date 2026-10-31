"""Implementation of 'strata compare' CLI command."""

from __future__ import annotations

from pathlib import Path
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from strata.evidence.comparison import RunComparator
from strata.storage.database import DatabaseManager
from strata.storage.repository import RunRepository

console = Console()


def compare_command(
    run_a: str = typer.Argument(
        ...,
        help="Baseline run identifier (e.g. run_42a8b9c0)",
    ),
    run_b: str = typer.Argument(
        ...,
        help="Comparison run identifier (e.g. run_98f7e6d5)",
    ),
    artifacts_dir: Path = typer.Option(
        Path("./artifacts"),
        "--artifacts-dir",
        "-d",
        help="Directory where experiment artifacts and database are stored",
    ),
) -> None:
    """Compare two completed experiment runs and compute differential analysis."""
    if artifacts_dir.is_file() and artifacts_dir.name.endswith(".db"):
        db_path = artifacts_dir
        actual_artifacts_dir = artifacts_dir.parent
    else:
        db_path = artifacts_dir / "strata_runs.db"
        actual_artifacts_dir = artifacts_dir

    if not db_path.exists():
        console.print(f"[bold red]Error:[/] Database not found at '{db_path}'. Has an experiment been run?")
        raise typer.Exit(code=1)

    db_mgr = DatabaseManager(db_path)
    repo = RunRepository(db_mgr)

    id_a = Path(run_a).name
    record_a = repo.get_run(run_a) or (repo.get_run(id_a) if id_a != run_a else None)
    if record_a is None:
        console.print(f"[bold red]Error:[/] Run A '{run_a}' not found in database.")
        recent_runs = repo.list_runs(limit=5)
        if recent_runs:
            console.print("[dim]Recent available runs:[/]")
            for r in recent_runs:
                console.print(f"  • [bold cyan]{r.run_id}[/] ({r.experiment_id})")
        raise typer.Exit(code=1)

    id_b = Path(run_b).name
    record_b = repo.get_run(run_b) or (repo.get_run(id_b) if id_b != run_b else None)
    if record_b is None:
        console.print(f"[bold red]Error:[/] Run B '{run_b}' not found in database.")
        recent_runs = repo.list_runs(limit=5)
        if recent_runs:
            console.print("[dim]Recent available runs:[/]")
            for r in recent_runs:
                console.print(f"  • [bold cyan]{r.run_id}[/] ({r.experiment_id})")
        raise typer.Exit(code=1)

    comparison = RunComparator.compare_records(record_a, record_b, artifacts_dir=actual_artifacts_dir)
    m = comparison.metrics

    # 1. Header Panel
    console.print(
        Panel.fit(
            f"Baseline (Run A): [bold cyan]{record_a.run_id}[/] ({record_a.experiment_id})\n"
            f"Target   (Run B): [bold cyan]{record_b.run_id}[/] ({record_b.experiment_id})\n"
            f"Database: {db_path}",
            title=f"Differential Run Comparison — {record_a.run_id} vs {record_b.run_id}",
            border_style="cyan",
        )
    )

    # 2. High-Level Metrics Comparison Table
    metrics_table = Table(title="Execution Metrics Comparison", border_style="dim")
    metrics_table.add_column("Metric", style="bold")
    metrics_table.add_column(f"Run A ({record_a.run_id})", style="cyan")
    metrics_table.add_column(f"Run B ({record_b.run_id})", style="cyan")
    metrics_table.add_column("Delta / Status", justify="center")

    # Status row
    status_delta = "[bold green]MATCH[/]" if m.status_match else "[bold yellow]CHANGED[/]"
    metrics_table.add_row("Execution Status", m.status_a.upper(), m.status_b.upper(), status_delta)

    # Seed row
    seed_delta = "[bold green]MATCH[/]" if m.seed_match else "[bold yellow]DIFFERENT[/]"
    metrics_table.add_row("Random Seed", str(m.seed_a), str(m.seed_b), seed_delta)

    # Virtual Duration row
    vt_delta_str = f"{m.virtual_time_delta_us:+,} us" if m.virtual_time_delta_us != 0 else "[dim]0 us[/]"
    metrics_table.add_row("Virtual Duration", f"{m.virtual_time_a_us:,} us", f"{m.virtual_time_b_us:,} us", vt_delta_str)

    # Events row
    ev_delta_str = f"{m.events_delta:+,}" if m.events_delta != 0 else "[dim]0[/]"
    metrics_table.add_row("Events Processed", f"{m.events_a:,}", f"{m.events_b:,}", ev_delta_str)

    # Wall-Clock row
    wc_delta_str = f"{m.wall_clock_delta_s:+.4f} s" if abs(m.wall_clock_delta_s) > 1e-6 else "[dim]0.0000 s[/]"
    metrics_table.add_row("Wall-Clock Duration", f"{m.wall_clock_a_s:.4f} s", f"{m.wall_clock_b_s:.4f} s", wc_delta_str)

    # Invariants row
    inv_a_str = "[bold green]PASSED[/]" if m.all_invariants_passed_a else "[bold red]FAILED[/]"
    inv_b_str = "[bold green]PASSED[/]" if m.all_invariants_passed_b else "[bold red]FAILED[/]"
    if m.invariants_verdict_match:
        inv_delta_str = "[bold green]MATCH[/]"
    elif m.all_invariants_passed_a and not m.all_invariants_passed_b:
        inv_delta_str = "[bold red]REGRESSION[/]"
    else:
        inv_delta_str = "[bold green]IMPROVEMENT[/]"
    metrics_table.add_row("All Invariants", inv_a_str, inv_b_str, inv_delta_str)

    console.print(metrics_table)

    # 3. Invariants Comparison Table
    if comparison.invariants:
        inv_table = Table(title="Invariant Verdicts Comparison", border_style="dim")
        inv_table.add_column("Invariant ID", style="bold")
        inv_table.add_column("Type", style="cyan")
        inv_table.add_column(f"Run A ({record_a.run_id})", justify="center")
        inv_table.add_column(f"Run B ({record_b.run_id})", justify="center")
        inv_table.add_column("Delta", justify="center")

        for inv in comparison.invariants:
            badge_a = (
                "[bold green]PASSED[/]" if inv.verdict_a == "passed"
                else (f"[bold red]{inv.verdict_a.upper()}[/]" if inv.verdict_a else "[dim]N/A[/]")
            )
            badge_b = (
                "[bold green]PASSED[/]" if inv.verdict_b == "passed"
                else (f"[bold red]{inv.verdict_b.upper()}[/]" if inv.verdict_b else "[dim]N/A[/]")
            )

            if inv.delta_status == "UNCHANGED":
                status_badge = "[dim]UNCHANGED[/]"
            elif inv.delta_status == "REGRESSION":
                status_badge = "[bold red]REGRESSION[/]"
            elif inv.delta_status == "IMPROVED":
                status_badge = "[bold green]IMPROVED[/]"
            elif inv.delta_status == "ADDED":
                status_badge = "[bold cyan]ADDED[/]"
            elif inv.delta_status == "REMOVED":
                status_badge = "[bold yellow]REMOVED[/]"
            else:
                status_badge = "[bold yellow]DIVERGENT[/]"

            inv_table.add_row(
                inv.invariant_id,
                inv.invariant_type,
                badge_a,
                badge_b,
                status_badge,
            )

        console.print(inv_table)

    # 4. Node State Diff Table
    if not comparison.node_diffs:
        console.print("[dim]No node state snapshots recorded for comparison.[/]")
    elif not comparison.has_node_state_divergence:
        console.print("[bold green]✓ Node States:[/] All replica states are identical between both runs.")
    else:
        state_table = Table(title="Node State Differences", border_style="dim")
        state_table.add_column("Node ID", style="bold")
        state_table.add_column("Key", style="cyan")
        state_table.add_column(f"Run A ({record_a.run_id})")
        state_table.add_column(f"Run B ({record_b.run_id})")
        state_table.add_column("Diff", justify="center")

        diff_count = 0
        for node_id, node_diff in sorted(comparison.node_diffs.items()):
            for diff in node_diff.differences:
                diff_count += 1
                val_a_str = json.dumps(diff.val_a, default=str) if diff.val_a is not None else "[dim]<none>[/]"
                val_b_str = json.dumps(diff.val_b, default=str) if diff.val_b is not None else "[dim]<none>[/]"

                if diff.diff_type == "MODIFIED":
                    diff_badge = "[bold yellow]MODIFIED[/]"
                elif diff.diff_type == "ONLY_IN_A":
                    diff_badge = "[bold red]ONLY_IN_A[/]"
                elif diff.diff_type == "ONLY_IN_B":
                    diff_badge = "[bold cyan]ONLY_IN_B[/]"
                else:
                    diff_badge = "[dim]MATCH[/]"

                state_table.add_row(
                    node_id,
                    diff.key,
                    val_a_str,
                    val_b_str,
                    diff_badge,
                )

        if diff_count > 0:
            console.print(state_table)
        else:
            console.print("[bold green]✓ Node States:[/] No divergent keys found.")
