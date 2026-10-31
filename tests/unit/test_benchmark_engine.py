"""Unit tests for BenchmarkRunner and BenchmarkResult aggregation."""

from __future__ import annotations

from pathlib import Path
import pytest

from strata.analysis.benchmark import (
    BenchmarkConfig,
    BenchmarkResult,
    BenchmarkRunner,
    BenchmarkSample,
)
from strata.core.experiment import (
    ArtifactsConfig,
    ExecutionConfig,
    ExperimentDefinition,
    ExperimentMetadata,
    NetworkConfig,
    NodeConfig,
    TopologyConfig,
    WorkloadConfig,
)


@pytest.fixture
def benchmark_experiment() -> ExperimentDefinition:
    """Fixture experiment configured for fast benchmark runs."""
    return ExperimentDefinition(
        metadata=ExperimentMetadata(
            id="bench_test_01",
            name="Benchmark Unit Test Experiment",
        ),
        execution=ExecutionConfig(seed=42, deterministic=True),
        topology=TopologyConfig(
            nodes=[
                NodeConfig(id="node-1", role="coordinator"),
                NodeConfig(id="node-2", role="replica"),
            ],
            network=NetworkConfig(default_latency_us=500),
        ),
        workload=WorkloadConfig(
            workload_type="replicated_kv",
            operations_count=10,
            arrival_interval_us=1000,
            target_nodes=["node-1"],
        ),
        artifacts=ArtifactsConfig(persist_sqlite=False, persist_jsonl=False),
    )


def test_benchmark_config_validation() -> None:
    """BenchmarkConfig enforces minimum iteration counts and positive timeouts."""
    cfg = BenchmarkConfig(iterations=5, warmup_iterations=2)
    assert cfg.iterations == 5
    assert cfg.warmup_iterations == 2

    with pytest.raises(ValueError):
        BenchmarkConfig(iterations=0)

    with pytest.raises(ValueError):
        BenchmarkConfig(iterations=3, warmup_iterations=3)


def test_benchmark_runner_execution(benchmark_experiment: ExperimentDefinition) -> None:
    """BenchmarkRunner runs specified iterations and calculates distribution metrics."""
    config = BenchmarkConfig(
        iterations=3,
        warmup_iterations=1,
    )
    runner = BenchmarkRunner(config=config)
    result = runner.run(benchmark_experiment)

    assert isinstance(result, BenchmarkResult)
    assert result.experiment_id == "bench_test_01"
    assert result.total_trials == 3
    assert result.warmup_trials == 1
    # Only non-warmup samples are used for stats
    assert len(result.samples) == 2

    # Verify distribution metrics exist and have positive values
    assert result.throughput_events_per_sec.mean > 0.0
    assert result.throughput_events_per_sec.count == 2
    assert result.wall_clock_duration_s.mean > 0.0
    assert result.speedup_factor.mean > 0.0


def test_benchmark_result_serialization(benchmark_experiment: ExperimentDefinition) -> None:
    """BenchmarkResult serializes cleanly to JSON-compatible dictionary."""
    runner = BenchmarkRunner(config=BenchmarkConfig(iterations=2, warmup_iterations=0))
    result = runner.run(benchmark_experiment)

    data = result.to_dict()
    assert data["experiment_id"] == "bench_test_01"
    assert "metrics" in data
    assert "throughput_events_per_sec" in data["metrics"]
    assert "speedup_factor" in data["metrics"]
    assert len(data["samples"]) == 2
