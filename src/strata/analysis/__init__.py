"""Analysis, performance benchmarking, metrics distributions, and telemetry."""

from strata.analysis.benchmark import (
    BenchmarkConfig,
    BenchmarkResult,
    BenchmarkRunner,
    BenchmarkSample,
)
from strata.analysis.metrics import (
    MetricDistribution,
    calculate_distribution,
    calculate_percentiles,
    compute_throughput_metrics,
)
from strata.analysis.reports import (
    generate_markdown_report,
    save_benchmark_artifacts,
)
from strata.analysis.telemetry import (
    NoOpSpan,
    StrataTelemetry,
    configure_telemetry,
    get_telemetry,
)

__all__ = [
    "BenchmarkConfig",
    "BenchmarkResult",
    "BenchmarkRunner",
    "BenchmarkSample",
    "MetricDistribution",
    "NoOpSpan",
    "StrataTelemetry",
    "calculate_distribution",
    "calculate_percentiles",
    "compute_throughput_metrics",
    "configure_telemetry",
    "generate_markdown_report",
    "get_telemetry",
    "save_benchmark_artifacts",
]
