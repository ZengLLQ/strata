"""Unit tests for HttpServiceAdapter."""

from __future__ import annotations

import time
import pytest

from examples.http_test_server import TestHttpCluster
from strata.adapters.http import HttpServiceAdapter
from strata.core.errors import (
    DestructiveActionRefusalError,
    EnvironmentSetupError,
    FaultApplicationError,
)
from strata.core.experiment import FaultConfig, WorkloadConfig
from strata.simulation.events import FaultAppliedEvent, WorkloadOperationEvent


@pytest.fixture(scope="module")
def http_cluster() -> TestHttpCluster:
    """Spin up an in-process 3-node HTTP test cluster."""
    cluster = TestHttpCluster(base_port=18100)
    cluster.start()
    yield cluster
    cluster.stop()


def test_http_adapter_setup_and_health(http_cluster: TestHttpCluster) -> None:
    endpoints = {
        "node-1": "http://127.0.0.1:18101",
        "node-2": "http://127.0.0.1:18102",
        "node-3": "http://127.0.0.1:18103",
    }
    adapter = HttpServiceAdapter(endpoints=endpoints)

    # Pre-flight setup succeeds
    adapter.setup(timeout_seconds=5.0)
    assert adapter.health_check() is True


def test_http_adapter_setup_failure_on_unreachable_endpoint() -> None:
    bad_endpoints = {
        "node-dead": "http://127.0.0.1:19999",
    }
    adapter = HttpServiceAdapter(endpoints=bad_endpoints)
    with pytest.raises(EnvironmentSetupError) as exc_info:
        adapter.setup(timeout_seconds=1.0)
    assert "timed out" in str(exc_info.value)


def test_http_adapter_execute_workload(http_cluster: TestHttpCluster) -> None:
    endpoints = {
        "node-1": "http://127.0.0.1:18101",
        "node-2": "http://127.0.0.1:18102",
    }
    adapter = HttpServiceAdapter(endpoints=endpoints)

    workload = WorkloadConfig(
        workload_type="replicated_kv",
        operations_count=4,
        key_space_size=2,
        arrival_interval_us=0,
        target_nodes=["node-1"],
    )

    start_ns = time.time_ns()
    events = adapter.execute_workload(workload, start_ns)

    assert len(events) == 4
    for ev in events:
        assert isinstance(ev, WorkloadOperationEvent)
        assert ev.event_type == "workload.operation"
        assert ev.payload["operation_id"].startswith("op_")
        assert ev.payload["http_status"] == 200
        assert ev.payload["success"] is True
        assert ev.payload["latency_us"] >= 0


def test_http_adapter_fault_injection_lifecycle(http_cluster: TestHttpCluster) -> None:
    endpoints = {
        "node-1": "http://127.0.0.1:18101",
        "node-2": "http://127.0.0.1:18102",
        "node-3": "http://127.0.0.1:18103",
    }
    adapter = HttpServiceAdapter(endpoints=endpoints)

    # 1. Inject node_crash fault on node-2
    crash_fault = FaultConfig(
        id="f_crash_2",
        fault_type="node_crash",
        target="node-2",
        trigger_time_us=1000,
    )
    evt = adapter.inject_fault(crash_fault, time.time_ns())
    assert isinstance(evt, FaultAppliedEvent)
    assert evt.payload["fault_id"] == "f_crash_2"
    assert evt.payload["evidence"]["http_status"] == 200

    # Verify node-2 is now offline (health check fails)
    assert adapter.health_check() is False

    # 2. Inject node_restart fault on node-2
    restart_fault = FaultConfig(
        id="f_restart_2",
        fault_type="node_restart",
        target="node-2",
        trigger_time_us=2000,
    )
    evt_restart = adapter.inject_fault(restart_fault, time.time_ns())
    assert isinstance(evt_restart, FaultAppliedEvent)
    assert adapter.health_check() is True


def test_http_adapter_destructive_safety_refusal(http_cluster: TestHttpCluster) -> None:
    endpoints = {"node-1": "http://127.0.0.1:18101"}
    safe_adapter = HttpServiceAdapter(endpoints=endpoints, allow_destructive=False)

    dest_fault = FaultConfig(
        id="f_dest",
        fault_type="node_crash",
        target="node-1",
        trigger_time_us=0,
        parameters={"destructive": True},
    )

    with pytest.raises(DestructiveActionRefusalError):
        safe_adapter.inject_fault(dest_fault, time.time_ns())


def test_http_adapter_collect_results_and_teardown(http_cluster: TestHttpCluster) -> None:
    endpoints = {
        "node-1": "http://127.0.0.1:18101",
        "node-2": "http://127.0.0.1:18102",
    }
    adapter = HttpServiceAdapter(endpoints=endpoints)

    # Write a test key
    workload = WorkloadConfig(
        workload_type="replicated_kv",
        operations_count=1,
        target_nodes=["node-1"],
    )
    adapter.execute_workload(workload, time.time_ns())

    # Collect results
    results = adapter.collect_results()
    assert "node_states" in results
    assert "node-1" in results["node_states"]

    # Teardown clears state
    adapter.teardown()
    fresh_results = adapter.collect_results()
    assert fresh_results["node_states"]["node-1"] == {}
