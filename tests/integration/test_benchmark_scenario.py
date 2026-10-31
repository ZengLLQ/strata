"""Integration test executing multi-trial benchmark scenarios on simulation and integration clusters."""

from __future__ import annotations

from pathlib import Path
import pytest

from examples.http_test_server import TestHttpCluster
from strata.adapters.harness import IntegrationHarness
from strata.adapters.http import HttpServiceAdapter
from strata.analysis.benchmark import BenchmarkConfig, BenchmarkRunner
from strata.core.experiment import ExperimentDefinition


@pytest.fixture(scope="module")
def bench_http_cluster() -> TestHttpCluster:
    """Spin up an in-process 3-node HTTP cluster on ports 18401-18403."""
    cluster = TestHttpCluster(base_port=18400)
    cluster.start()
    yield cluster
    cluster.stop()


def test_simulation_benchmark_scenario() -> None:
    """Run benchmark against deterministic simulation model."""
    exp = ExperimentDefinition.from_yaml("examples/three_node_crash.yaml")

    runner = BenchmarkRunner(
        config=BenchmarkConfig(iterations=3, warmup_iterations=1)
    )
    result = runner.run(exp)

    assert result.total_trials == 3
    assert result.warmup_trials == 1
    assert len(result.samples) == 2
    assert result.throughput_events_per_sec.mean > 0
    assert result.speedup_factor.mean > 0


def test_integration_benchmark_scenario(bench_http_cluster: TestHttpCluster) -> None:
    """Run benchmark against real HTTP integration cluster."""
    endpoints = {
        "node-1": "http://127.0.0.1:18401",
        "node-2": "http://127.0.0.1:18402",
        "node-3": "http://127.0.0.1:18403",
    }
    exp = ExperimentDefinition.from_yaml("examples/integration_http_cluster.yaml")

    # Update endpoints to match test cluster
    updated_nodes = [
        node.model_copy(update={"parameters": {"endpoint": endpoints[node.id]}})
        for node in exp.topology.nodes
    ]
    exp = exp.model_copy(update={"topology": exp.topology.model_copy(update={"nodes": updated_nodes})})

    runner = BenchmarkRunner(
        config=BenchmarkConfig(iterations=2, warmup_iterations=0)
    )
    result = runner.run(exp)

    assert result.total_trials == 2
    assert len(result.samples) == 2
    assert result.throughput_events_per_sec.mean > 0
