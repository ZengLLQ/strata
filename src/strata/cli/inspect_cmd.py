"""Implementation of 'strata inspect' CLI command."""

from __future__ import annotations

import json
from pathlib import Path
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from strata.evidence.event_log import JsonlEventLogger
from strata.evidence.manifest import RunManifest
from strata.storage.database import DatabaseManager
from strata.storage.repository import RunRepository

console = Console()


def inspect_command(
    run_id: str = typer.Argument(
        ...,
        help="Run identifier to inspect (e.g. run_42a8b9c0)",
    ),
    artifacts_dir: Path = typer.Option(
        Path("./artifacts"),
        "--artifacts-dir",
        "-d",
        help="Directory where experiment artifacts and database are stored",
    ),
    show_events: bool = typer.Option(
        False,
        "--events",
        "-e",
        help="Display the chronological event timeline",
    ),
    limit: int = typer.Option(
        50,
        "--limit",
        "-n",
        help="Maximum number of timeline events to display",
    ),
) -> None:
    """Inspect execution details, invariants, and event history for a completed run."""
    db_path = artifacts_dir / "strata_runs.db"
    if not db_path.exists():
        console.print(f"[bold red]Error:[/] Database not found at '{db_path}'. Has an experiment been run?")
        raise typer.Exit(code=1)

    db_mgr = DatabaseManager(db_path)
    repo = RunRepository(db_mgr)
    run_record = repo.get_run(run_id)

    if run_record is None:
        recent_runs = repo.list_runs(limit=5)
        console.print(f"[bold red]Error:[/] Run '{run_id}' not found.")
        if recent_runs:
            console.print("[dim]Recent available runs:[/]")
            for r in recent_runs:
                console.print(f"  • [bold cyan]{r.run_id}[/] ({r.experiment_id}, status={r.status})")
        raise typer.Exit(code=1)

    # 1. Summary Panel
    status_style = "bold green" if run_record.status == "completed" else "bold red"
    invariants_badge = "[bold green]PASSED[/]" if run_record.all_invariants_passed == 1 else "[bold red]FAILED[/]"
    
    summary_data = {}
    if run_record.summary_json:
        try:
            summary_data = json.loads(run_record.summary_json)
        except Exception:
            pass
    exec_mode = summary_data.get("execution_mode", "simulation")
    mode_display = (
        "[bold magenta]INTEGRATION[/] (Real System / External Services)"
        if exec_mode == "integration"
        else "[bold cyan]SIMULATION[/] (Deterministic Discrete-Event)"
    )
    border_color = "magenta" if exec_mode == "integration" else "cyan"

    console.print(
        Panel.fit(
            f"Run ID: [bold]{run_record.run_id}[/]\n"
            f"Experiment: [bold cyan]{run_record.experiment_id}[/]\n"
            f"Mode: {mode_display}\n"
            f"Status: [{status_style}]{run_record.status.upper()}[/]\n"
            f"Seed: {run_record.seed}\n"
            f"Virtual Duration: [bold]{run_record.final_virtual_time_us:,}[/] us\n"
            f"Events Dispatched: [bold]{run_record.events_processed:,}[/]\n"
            f"Wall-Clock Duration: {run_record.wall_clock_duration_s:.4f} s\n"
            f"Invariants Status: {invariants_badge}\n"
            f"Recorded At: {run_record.created_at.isoformat() if hasattr(run_record, 'created_at') else 'N/A'}",
            title=f"Run Inspection — {run_record.run_id}",
            border_style=border_color,
        )
    )

    # 2. Invariant Records Table
    if run_record.invariant_records:
        inv_table = Table(title="Invariant Results", border_style="dim")
        inv_table.add_column("Invariant ID", style="bold")
        inv_table.add_column("Type", style="cyan")
        inv_table.add_column("Verdict", justify="center")
        inv_table.add_column("Explanation")

        for inv in run_record.invariant_records:
            badge = "[bold green]PASSED[/]" if inv.verdict == "passed" else f"[bold red]{inv.verdict.upper()}[/]"
            inv_table.add_row(
                inv.invariant_id,
                inv.invariant_type,
                badge,
                inv.explanation,
            )
        console.print(inv_table)

    # 3. Artifact Bundle Verification
    bundle_dir = artifacts_dir / run_record.run_id
    manifest_path = bundle_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = RunManifest.load_from(manifest_path)
            verification = manifest.verify_directory(bundle_dir)
            console.print(f"[bold green]✓ Manifest Verified:[/] {len(verification)} artifacts intact with matching SHA-256 digests.")
        except Exception as exc:
            console.print(f"[bold red]✗ Artifact Verification Failed:[/] {exc}")

    # 4. Chronological Event Timeline
    if show_events:
        events_file = bundle_dir / "events.jsonl"
        if not events_file.exists():
            console.print(f"[dim]Event log file not found at '{events_file}'.[/]")
            return

        events = JsonlEventLogger.read_events(events_file)
        displayed_events = events[:limit]

        timeline_table = Table(title=f"Event Timeline (showing {len(displayed_events)} of {len(events)} events)", border_style="dim")
        timeline_table.add_column("Seq", style="dim", justify="right")
        timeline_table.add_column("Virtual Time", justify="right", style="cyan")
        timeline_table.add_column("Priority", style="dim")
        timeline_table.add_column("Event Type", style="bold")
        timeline_table.add_column("Route")
        timeline_table.add_column("Summary")

        for e in displayed_events:
            route = f"{e.source or '*'} → {e.target or '*'}"
            summary = ""
            if e.event_type == "node.state_change":
                summary = f"{e.payload.get('previous_state')} → {e.payload.get('new_state')} ({e.payload.get('reason')})"
            elif e.event_type == "fault.applied":
                summary = f"fault={e.payload.get('fault_id')} ({e.payload.get('fault_type')})"
            elif e.event_type == "network.message_delivery":
                summary = f"msg={e.payload.get('message_type')}"
            elif e.event_type == "workload.operation":
                summary = f"{e.payload.get('op_type')}({e.payload.get('key')}={e.payload.get('value')})"
            else:
                summary = str(e.payload)[:40]

            timeline_table.add_row(
                str(e.sequence_id),
                f"{e.timestamp_us:,} us",
                e.priority.name,
                e.event_type,
                route,
                summary,
            )

        console.print(timeline_table)
        if len(events) > limit:
            console.print(f"[dim]Note: {len(events) - limit} additional events omitted. Use '--limit <N>' to see more.[/]")
