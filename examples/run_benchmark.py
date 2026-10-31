"""Example demonstrating programmatic performance benchmarking with BenchmarkRunner."""

from __future__ import annotations

from pathlib import Path
from rich import print as rprint

from strata.analysis.benchmark import BenchmarkConfig, BenchmarkRunner
from strata.analysis.reports import generate_markdown_report, save_benchmark_artifacts
from strata.core.experiment import ExperimentDefinition


def main() -> None:
    # 1. Load experiment specification
    exp_path = Path("examples/three_node_crash.yaml")
    rprint(f"[bold cyan]Loading experiment:[/] {exp_path}")
    experiment = ExperimentDefinition.from_yaml(exp_path)

    # 2. Configure benchmark sweep: 5 iterations, 1 warmup
    cfg = BenchmarkConfig(
        iterations=5,
        warmup_iterations=1,
        seed_step=10,
        output_dir="./artifacts/benchmarks",
    )
    rprint(f"Executing [bold]{cfg.iterations}[/] trials ({cfg.warmup_iterations} warmup, {cfg.iterations - cfg.warmup_iterations} measured)...")

    # 3. Run benchmark
    runner = BenchmarkRunner(config=cfg)

    def on_progress(cur: int, tot: int, is_warmup: bool) -> None:
        stage = "warmup" if is_warmup else "measured"
        rprint(f"  • Running trial {cur}/{tot} ({stage})...")

    result = runner.run(experiment, progress_callback=on_progress)

    # 4. Display results
    rprint("\n[bold green]Benchmark Completed![/]")
    rprint(f"  Experiment: {result.experiment_id} ({result.execution_mode})")
    rprint(f"  Mean Throughput: [bold green]{result.throughput_events_per_sec.mean:,.1f}[/] events/s (±{result.throughput_events_per_sec.stddev:,.1f})")
    rprint(f"  Speedup Factor: [bold]{result.speedup_factor.mean:.2f}x[/] (virtual / wall-clock)")
    rprint(f"  Wall-Clock Duration: {result.wall_clock_duration_s.mean:.4f}s [min: {result.wall_clock_duration_s.min:.4f}s, max: {result.wall_clock_duration_s.max:.4f}s]")

    # 5. Persist artifacts
    json_path, md_path = save_benchmark_artifacts(
        result=result,
        output_dir=cfg.output_dir,
        save_markdown=True,
    )
    rprint(f"\nSaved artifacts to: {cfg.output_dir}")
    rprint(f"  • JSON: {json_path}")
    rprint(f"  • Markdown: {md_path}")


if __name__ == "__main__":
    main()
