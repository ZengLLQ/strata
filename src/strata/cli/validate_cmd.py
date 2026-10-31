"""Implementation of 'strata validate' CLI command."""

from __future__ import annotations

from pathlib import Path
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from strata.core.errors import ConfigurationError
from strata.core.experiment import ExperimentDefinition

console = Console()


def validate_command(
    path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to experiment specification YAML file",
    ),
) -> None:
    """Validate an experiment definition without executing it."""
    try:
        exp = ExperimentDefinition.from_yaml(path)
    except ConfigurationError as err:
        console.print(f"[bold red]Validation Failed:[/] {err}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected Error:[/] {exc}")
        raise typer.Exit(code=1)

    # Render summary presentation
    console.print(
        Panel.fit(
            f"[bold cyan]{exp.metadata.name}[/] [dim]({exp.metadata.id} v{exp.metadata.version})[/]\n"
            f"[italic]{exp.metadata.description or 'No description provided.'}[/]",
            title="Experiment Specification Valid",
            border_style="green",
        )
    )

    # Topology Summary Table
    topo_table = Table(title="Topology", border_style="dim")
    topo_table.add_column("Node ID", style="bold")
    topo_table.add_column("Role", style="cyan")
    topo_table.add_column("Initial State")
    for node in exp.topology.nodes:
        topo_table.add_row(node.id, node.role, node.initial_state.value)
    console.print(topo_table)

    # Faults Summary Table
    if exp.faults:
        fault_table = Table(title="Scheduled Faults", border_style="dim")
        fault_table.add_column("Fault ID", style="bold")
        fault_table.add_column("Type", style="yellow")
        fault_table.add_column("Target", style="cyan")
        fault_table.add_column("Trigger (us)", justify="right")
        fault_table.add_column("Duration (us)", justify="right")
        for f in exp.faults:
            fault_table.add_row(
                f.id,
                f.fault_type,
                f.target,
                str(f.trigger_time_us),
                str(f.duration_us) if f.duration_us is not None else "indefinite",
            )
        console.print(fault_table)

    # Invariants Summary Table
    if exp.invariants:
        inv_table = Table(title="Invariants", border_style="dim")
        inv_table.add_column("Invariant ID", style="bold")
        inv_table.add_column("Type", style="magenta")
        inv_table.add_column("Description")
        for inv in exp.invariants:
            inv_table.add_row(inv.id, inv.invariant_type, inv.description)
        console.print(inv_table)

    console.print("\n[bold green]✓ Configuration is structurally and semantically valid.[/]")
