"""Statistical metrics calculations and distribution analysis for Strata benchmarks."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Sequence


@dataclass(frozen=True)
class MetricDistribution:
    """Statistical summary distribution for a numerical metric series."""

    count: int
    min: float
    max: float
    mean: float
    median: float
    stddev: float
    p90: float
    p95: float
    p99: float

    def to_dict(self) -> dict[str, float | int]:
        return {
            "count": self.count,
            "min": round(self.min, 4),
            "max": round(self.max, 4),
            "mean": round(self.mean, 4),
            "median": round(self.median, 4),
            "stddev": round(self.stddev, 4),
            "p90": round(self.p90, 4),
            "p95": round(self.p95, 4),
            "p99": round(self.p99, 4),
        }


def calculate_percentiles(
    values: Sequence[float],
    percentiles: Sequence[int | float],
) -> dict[int | float, float]:
    """Calculate specified percentiles from a sequence of numerical values using linear interpolation."""
    if not values:
        return {p: 0.0 for p in percentiles}

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    results: dict[int | float, float] = {}

    for p in percentiles:
        if p <= 0:
            results[p] = sorted_vals[0]
            continue
        if p >= 100:
            results[p] = sorted_vals[-1]
            continue

        rank = (p / 100.0) * (n - 1)
        lower_idx = int(rank)
        upper_idx = min(lower_idx + 1, n - 1)
        weight = rank - lower_idx
        interpolated = sorted_vals[lower_idx] + weight * (sorted_vals[upper_idx] - sorted_vals[lower_idx])
        results[p] = float(interpolated)

    return results


def calculate_distribution(values: Sequence[float]) -> MetricDistribution:
    """Compute complete statistical distribution over a sequence of numerical samples."""
    count = len(values)
    if count == 0:
        return MetricDistribution(
            count=0,
            min=0.0,
            max=0.0,
            mean=0.0,
            median=0.0,
            stddev=0.0,
            p90=0.0,
            p95=0.0,
            p99=0.0,
        )

    if count == 1:
        val = float(values[0])
        return MetricDistribution(
            count=1,
            min=val,
            max=val,
            mean=val,
            median=val,
            stddev=0.0,
            p90=val,
            p95=val,
            p99=val,
        )

    mean_val = float(sum(values) / count)
    variance = sum((x - mean_val) ** 2 for x in values) / (count - 1)
    stddev_val = float(math.sqrt(max(0.0, variance)))

    percentiles = calculate_percentiles(values, [50, 90, 95, 99])

    return MetricDistribution(
        count=count,
        min=float(min(values)),
        max=float(max(values)),
        mean=mean_val,
        median=percentiles[50],
        stddev=stddev_val,
        p90=percentiles[90],
        p95=percentiles[95],
        p99=percentiles[99],
    )


def compute_throughput_metrics(
    events_processed: int,
    operations_count: int,
    wall_clock_duration_s: float,
) -> dict[str, float]:
    """Compute events/second and operations/second throughput rates."""
    if wall_clock_duration_s <= 0.0:
        return {
            "events_per_second": 0.0,
            "operations_per_second": 0.0,
        }

    return {
        "events_per_second": float(events_processed / wall_clock_duration_s),
        "operations_per_second": float(operations_count / wall_clock_duration_s),
    }
