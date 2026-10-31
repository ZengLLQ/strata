"""Implementation of 'strata benchmark' CLI command."""

from __future__ import annotations

from pathlib import Path
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from strata.analysis.benchmark import BenchmarkConfig, BenchmarkRunner
from strata.analysis.reports import save_benchmark_artifacts
from strata.core.errors import ConfigurationError
from strata.core.experiment import ExperimentDefinition

console = Console()


def benchmark_command(
    path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Path to experiment specification YAML file",
    ),
    iterations: int = typer.Option(
        5,
        "--iterations",
        "-n",
        min=1,
        help="Total benchmark iterations to execute",
    ),
    warmup: int = typer.Option(
        1,
        "--warmup",
        "-w",
        min=0,
        help="Number of initial warmup iterations to discard from statistics",
    ),
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Directory where benchmark summary and report will be written",
    ),
    save_json: bool = typer.Option(
        True,
        "--json/--no-json",
        help="Save structured benchmark_summary.json",
    ),
    save_markdown: bool = typer.Option(
        True,
        "--markdown/--no-markdown",
        help="Save human-readable benchmark_report.md",
    ),
) -> None:
    """Benchmark performance, throughput, and speedup across multiple experiment trials."""
    # 1. Load experiment specification
    try:
        exp = ExperimentDefinition.from_yaml(path)
    except ConfigurationError as err:
        console.print(f"[bold red]Configuration Error:[/] {err}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Error Loading Experiment:[/] {exc}")
        raise typer.Exit(code=1)

    # 2. Build configuration
    target_out_dir = output_dir or Path(exp.artifacts.output_dir)
    target_out_dir.mkdir(parents=True, exist_ok=True)

    try:
        cfg = BenchmarkConfig(
            iterations=iterations,
            warmup_iterations=warmup,
            output_dir=str(target_out_dir),
        )
    except ValueError as val_err:
        console.print(f"[bold red]Benchmark Parameter Error:[/] {val_err}")
        raise typer.Exit(code=1)

    mode_label = (
        "[bold magenta]INTEGRATION[/] (Real System / External Services)"
        if exp.execution.mode.value == "integration"
        else "[bold cyan]SIMULATION[/] (Deterministic Discrete-Event)"
    )

    console.print(f"\n[bold]Benchmarking Experiment:[/] [cyan]{exp.metadata.name}[/]")
    console.print(f"Execution Mode: {mode_label}")
    console.print(f"Trials: [bold]{iterations}[/] ({warmup} warmup, {iterations - warmup} measured)\n")

    # 3. Execute benchmark sweep with progress indicator
    runner = BenchmarkRunner(config=cfg)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as progress:
        task_id = progress.add_task(description="Running benchmark trials...", total=iterations)

        def on_trial_update(current: int, total: int, is_warmup: bool) -> None:
            kind = "warmup" if is_warmup else "measured"
            progress.update(task_id, description=f"Executing trial {current}/{total} ({kind})...", completed=current)

        result = runner.run(exp, progress_callback=on_trial_update)

    # 4. Render Summary Panel
    panel_border = "magenta" if exp.execution.mode.value == "integration" else "cyan"
    console.print(
        Panel.fit(
            f"Experiment ID: [bold]{result.experiment_id}[/]\n"
            f"Total Trials: [bold]{result.total_trials}[/] ({result.warmup_trials} warmup, {len(result.samples)} measured)\n"
            f"Throughput Mean: [bold green]{result.throughput_events_per_sec.mean:,.1f}[/] events/s (±{result.throughput_events_per_sec.stddev:,.1f})\n"
            f"Ops Throughput: [bold green]{result.throughput_ops_per_sec.mean:,.1f}[/] ops/s\n"
            f"Speedup Factor: [bold]{result.speedup_factor.mean:.2f}x[/] (virtual / wall-clock time)\n"
            f"Mean Wall Duration: [bold]{result.wall_clock_duration_s.mean:.4f}[/] s (min: {result.wall_clock_duration_s.min:.4f}s, max: {result.wall_clock_duration_s.max:.4f}s)",
            title="Benchmark Completed",
            border_style=panel_border,
        )
    )

    # 5. Statistical Distributions Table
    dist_table = Table(title="Statistical Distributions (Measured Trials)", border_style="dim")
    dist_table.add_column("Metric", style="bold")
    dist_table.add_column("Mean", justify="right")
    dist_table.add_column("StdDev", justify="right")
    dist_table.add_column("Min", justify="right")
    dist_table.add_column("Median (p50)", justify="right")
    dist_table.add_column("p90", justify="right")
    dist_table.add_column("p95", justify="right")
    dist_table.add_column("Max", justify="right")

    metrics_rows = [
        ("Throughput (Events/s)", result.throughput_events_per_sec),
        ("Throughput (Ops/s)", result.throughput_ops_per_sec),
        ("Speedup Factor", result.speedup_factor),
        ("Wall Time (s)", result.wall_clock_duration_s),
        ("Events Dispatched", result.events_processed),
    ]

    for name, dist in metrics_rows:
        dist_table.add_row(
            name,
            f"{dist.mean:,.2f}",
            f"{dist.stddev:,.2f}",
            f"{dist.min:,.2f}",
            f"{dist.median:,.2f}",
            f"{dist.p90:,.2f}",
            f"{dist.p95:,.2f}",
            f"{dist.max:,.2f}",
        )
    console.print(dist_table)

    # 6. Save Artifacts
    json_path, md_path = save_benchmark_artifacts(
        result=result,
        output_dir=target_out_dir,
        save_markdown=save_markdown,
    )

    console.print("\n[dim]Artifacts generated:[/]")
    if json_path:
        console.print(f"  • JSON Summary: [bold cyan]{json_path}[/]")
    if md_path:
        console.print(f"  • Markdown Report: [bold cyan]{md_path}[/]")
