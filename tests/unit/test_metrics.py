"""Unit tests for statistical metrics calculations and distribution analysis."""

from __future__ import annotations

import math
import pytest

from strata.analysis.metrics import (
    MetricDistribution,
    calculate_distribution,
    calculate_percentiles,
    compute_throughput_metrics,
)


def test_calculate_distribution_empty() -> None:
    """Empty list returns zeroed distribution with count=0."""
    dist = calculate_distribution([])
    assert dist.count == 0
    assert dist.mean == 0.0
    assert dist.median == 0.0
    assert dist.p90 == 0.0
    assert dist.p95 == 0.0
    assert dist.p99 == 0.0
    assert dist.min == 0.0
    assert dist.max == 0.0
    assert dist.stddev == 0.0


def test_calculate_distribution_single_value() -> None:
    """Single value returns that value across all percentiles with zero stddev."""
    dist = calculate_distribution([42.0])
    assert dist.count == 1
    assert dist.mean == 42.0
    assert dist.median == 42.0
    assert dist.p90 == 42.0
    assert dist.p95 == 42.0
    assert dist.p99 == 42.0
    assert dist.min == 42.0
    assert dist.max == 42.0
    assert dist.stddev == 0.0


def test_calculate_distribution_multi_values() -> None:
    """Calculates accurate mean, median, min, max, and percentiles."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    dist = calculate_distribution(values)

    assert dist.count == 10
    assert dist.min == 1.0
    assert dist.max == 10.0
    assert dist.mean == 5.5
    assert dist.median == 5.5
    assert dist.stddev > 0.0
    assert dist.p90 >= 9.0
    assert dist.p95 >= 9.5
    assert dist.p99 <= 10.0


def test_calculate_percentiles_nearest_rank() -> None:
    """Verify percentile calculation for standard percentiles."""
    data = [i for i in range(1, 101)]  # 1 to 100
    p50 = calculate_percentiles(data, [50])[50]
    p90 = calculate_percentiles(data, [90])[90]
    p95 = calculate_percentiles(data, [95])[95]
    p99 = calculate_percentiles(data, [99])[99]

    assert 49.0 <= p50 <= 51.0
    assert 89.0 <= p90 <= 91.0
    assert 94.0 <= p95 <= 96.0
    assert 98.0 <= p99 <= 100.0


def test_compute_throughput_metrics() -> None:
    """Verify events and operations per second throughput calculation."""
    throughput = compute_throughput_metrics(
        events_processed=50000,
        operations_count=1000,
        wall_clock_duration_s=0.5,
    )

    assert throughput["events_per_second"] == 100000.0
    assert throughput["operations_per_second"] == 2000.0


def test_compute_throughput_metrics_zero_duration() -> None:
    """Zero duration handles division by zero safely."""
    throughput = compute_throughput_metrics(
        events_processed=100,
        operations_count=10,
        wall_clock_duration_s=0.0,
    )
    assert throughput["events_per_second"] == 0.0
    assert throughput["operations_per_second"] == 0.0
