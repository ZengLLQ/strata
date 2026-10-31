"""Unit tests for StrataTelemetry provider and OpenTelemetry integration."""

from __future__ import annotations

import pytest

from strata.analysis.telemetry import (
    NoOpSpan,
    StrataTelemetry,
    get_telemetry,
)


def test_telemetry_disabled_by_default() -> None:
    """Telemetry provider defaults to safe no-op mode without overhead."""
    telemetry = StrataTelemetry(enabled=False)
    assert telemetry.enabled is False

    with telemetry.trace_span("test_span") as span:
        assert isinstance(span, NoOpSpan)
        span.set_attribute("key", "val")

    # Metrics recordings are safe no-ops
    telemetry.record_counter("events.dispatched", 10)
    telemetry.record_histogram("latency_us", 150.0)


def test_telemetry_in_memory_collector() -> None:
    """When enabled with in-memory collection, spans and metrics are tracked."""
    telemetry = StrataTelemetry(enabled=True, in_memory=True)
    assert telemetry.enabled is True

    with telemetry.trace_span("workload.op", attributes={"key": "k1"}) as span:
        span.set_attribute("status", 200)

    telemetry.record_counter("strata.events.total", 5)
    telemetry.record_histogram("strata.latency.us", 120.0)

    records = telemetry.get_in_memory_records()
    assert len(records["spans"]) == 1
    assert records["spans"][0]["name"] == "workload.op"
    assert records["spans"][0]["attributes"]["key"] == "k1"
    assert records["spans"][0]["attributes"]["status"] == 200

    assert "strata.events.total" in records["counters"]
    assert records["counters"]["strata.events.total"] == 5

    assert "strata.latency.us" in records["histograms"]
    assert records["histograms"]["strata.latency.us"] == [120.0]


def test_get_telemetry_singleton() -> None:
    """get_telemetry returns consistent telemetry instance."""
    t1 = get_telemetry()
    t2 = get_telemetry()
    assert t1 is t2
