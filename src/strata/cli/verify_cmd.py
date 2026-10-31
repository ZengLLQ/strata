"""Implementation of 'strata verify' CLI command."""

from __future__ import annotations

from pathlib import Path
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from strata.core.errors import ArtifactIntegrityError
from strata.evidence.manifest import RunManifest

console = Console()


def verify_command(
    run_id: str = typer.Argument(
        ...,
        help="Run identifier to verify (e.g. run_42a8b9c0)",
    ),
    artifacts_dir: Path = typer.Option(
        Path("./artifacts"),
        "--artifacts-dir",
        "-d",
        help="Directory where experiment artifacts are stored",
    ),
) -> None:
    """Verify cryptographic integrity of an experiment run artifact bundle against its manifest."""
    candidate = Path(run_id)
    if (artifacts_dir / run_id).is_dir():
        bundle_dir = artifacts_dir / run_id
    elif candidate.is_dir():
        bundle_dir = candidate
    elif (artifacts_dir / candidate.name).is_dir():
        bundle_dir = artifacts_dir / candidate.name
    else:
        bundle_dir = artifacts_dir / run_id

    if not bundle_dir.exists():
        console.print(f"[bold red]Error:[/] Artifact bundle directory not found at '{bundle_dir}'.")
        raise typer.Exit(code=1)

    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        console.print(f"[bold red]Error:[/] Manifest file 'manifest.json' not found in '{bundle_dir}'.")
        raise typer.Exit(code=1)

    try:
        manifest = RunManifest.load_from(manifest_path)
    except Exception as exc:
        console.print(f"[bold red]Error:[/] Failed to parse manifest at '{manifest_path}': {exc}")
        raise typer.Exit(code=1)

    # Required core artifacts per Strata evidence specification
    required_artifacts = ["experiment.yaml", "events.jsonl", "run_summary.json"]
    for req in required_artifacts:
        if req not in manifest.artifacts:
            console.print(f"[bold red]Error:[/] Required artifact '{req}' is not recorded in manifest.json.")
            raise typer.Exit(code=1)
        req_file = bundle_dir / req
        if not req_file.exists():
            console.print(f"[bold red]Error:[/] Required artifact file '{req}' is missing from disk.")
            raise typer.Exit(code=1)

    try:
        verification_results = manifest.verify_directory(bundle_dir)
    except ArtifactIntegrityError as exc:
        console.print(f"[bold red]Verification Failed:[/] Artifact integrity violation: {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Verification Failed:[/] Error during checksum verification: {exc}")
        raise typer.Exit(code=1)

    # 1. Summary Panel
    console.print(
        Panel.fit(
            f"Run ID: [bold]{manifest.run_id}[/]\n"
            f"Experiment: [bold cyan]{manifest.experiment_id}[/]\n"
            f"Seed: {manifest.seed}\n"
            f"Engine Version: {manifest.engine_version}\n"
            f"Bundle Directory: {bundle_dir}",
            title=f"Artifact Verification — {manifest.run_id}",
            border_style="green",
        )
    )

    # 2. Artifact Checksums Table
    table = Table(title="Verified Artifact Digests (SHA-256)", border_style="dim")
    table.add_column("Artifact File", style="bold")
    table.add_column("SHA-256 Checksum", style="dim")
    table.add_column("Integrity", justify="center")

    for filename, digest in sorted(manifest.artifacts.items()):
        table.add_row(
            filename,
            digest,
            "[bold green]VERIFIED[/]",
        )

    console.print(table)
    console.print(
        f"[bold green]✓ Artifact Bundle Verified:[/] All {len(verification_results)} artifacts intact with matching SHA-256 digests."
    )
