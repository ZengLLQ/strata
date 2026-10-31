"""Unit tests for the 'strata benchmark' CLI command."""

from __future__ import annotations

from pathlib import Path
import pytest
from typer.testing import CliRunner

from strata.cli.main import app

runner = CliRunner()


def test_benchmark_cli_help() -> None:
    """Verify 'strata benchmark --help' displays usage information."""
    result = runner.invoke(app, ["benchmark", "--help"])
    assert result.exit_code == 0
    assert "benchmark" in result.stdout.lower()
    assert "--iterations" in result.stdout
    assert "--warmup" in result.stdout


def test_benchmark_cli_execution(tmp_path: Path) -> None:
    """Run benchmark command against sample experiment and verify output."""
    exp_file = Path("examples/three_node_crash.yaml")
    out_dir = tmp_path / "bench_out"

    result = runner.invoke(
        app,
        [
            "benchmark",
            str(exp_file),
            "--iterations",
            "2",
            "--warmup",
            "1",
            "--output-dir",
            str(out_dir),
            "--json",
            "--markdown",
        ],
    )

    assert result.exit_code == 0
    assert "Benchmark Completed" in result.stdout or "Throughput" in result.stdout

    # Verify generated report artifacts
    summary_json = out_dir / "benchmark_summary.json"
    report_md = out_dir / "benchmark_report.md"

    assert summary_json.exists()
    assert report_md.exists()

    content = summary_json.read_text(encoding="utf-8")
    assert "throughput_events_per_sec" in content


def test_benchmark_cli_invalid_path() -> None:
    """Non-existent experiment path returns error code 2 (Typer file validation)."""
    result = runner.invoke(app, ["benchmark", "nonexistent.yaml"])
    assert result.exit_code != 0
