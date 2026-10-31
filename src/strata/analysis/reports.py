"""Markdown and structured JSON report generation for benchmark results."""

from __future__ import annotations

import json
from pathlib import Path

from strata.analysis.benchmark import BenchmarkResult


def generate_markdown_report(result: BenchmarkResult) -> str:
    """Format benchmark results into a clean GitHub Flavored Markdown report."""
    mode_label = "Real-System Integration" if result.execution_mode == "integration" else "Deterministic Simulation"

    lines = [
        f"# Strata Benchmark Report: {result.experiment_id}",
        "",
        f"**Execution Mode**: {mode_label} (`{result.execution_mode}`)",
        f"**Total Trials**: {result.total_trials} ({result.warmup_trials} warmup, {len(result.samples)} measured)",
        "",
        "## Performance Distribution",
        "",
        "| Metric | Mean | StdDev | Min | Median (p50) | p90 | p95 | p99 | Max |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]

    metric_rows = [
        ("Throughput (Events/s)", result.throughput_events_per_sec),
        ("Throughput (Ops/s)", result.throughput_ops_per_sec),
        ("Speedup Factor (Virtual/Wall)", result.speedup_factor),
        ("Wall-Clock Time (s)", result.wall_clock_duration_s),
        ("Events Dispatched", result.events_processed),
    ]

    for name, dist in metric_rows:
        lines.append(
            f"| **{name}** | {dist.mean:,.2f} | {dist.stddev:,.2f} | {dist.min:,.2f} | "
            f"{dist.median:,.2f} | {dist.p90:,.2f} | {dist.p95:,.2f} | {dist.p99:,.2f} | {dist.max:,.2f} |"
        )

    lines.extend([
        "",
        "## Individual Trial Samples",
        "",
        "| Trial | Seed | Events | Wall Time (s) | Throughput (ev/s) | Speedup | Invariants |",
        "| :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
    ])

    for s in result.samples:
        badge = "PASSED" if s.all_invariants_passed else "FAILED"
        lines.append(
            f"| #{s.trial_index + 1} | {s.seed} | {s.events_processed:,} | "
            f"{s.wall_clock_duration_s:.4f}s | {s.throughput_events_per_sec:,.1f} | {s.speedup_factor:.2f}x | {badge} |"
        )

    lines.append("")
    return "\n".join(lines)


def save_benchmark_artifacts(
    result: BenchmarkResult,
    output_dir: Path | str,
    save_markdown: bool = True,
) -> tuple[Path, Path | None]:
    """Persist benchmark JSON summary and optional Markdown report to disk."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    json_path = out_path / "benchmark_summary.json"
    json_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

    md_path: Path | None = None
    if save_markdown:
        md_path = out_path / "benchmark_report.md"
        md_path.write_text(generate_markdown_report(result), encoding="utf-8")

    return json_path, md_path
