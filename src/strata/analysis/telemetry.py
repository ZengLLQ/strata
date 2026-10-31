"""OpenTelemetry instrumentation provider with zero-dependency fallback."""

from __future__ import annotations

from contextlib import contextmanager
import time
from typing import Any, Generator, Mapping


class NoOpSpan:
    """Null-object span pattern when OpenTelemetry SDK is absent or disabled."""

    def __init__(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        self.name = name
        self.attributes: dict[str, Any] = dict(attributes or {})
        self.start_time = time.monotonic()
        self.end_time: float | None = None

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_status(self, status: str, description: str | None = None) -> None:
        self.attributes["otel.status_code"] = status
        if description:
            self.attributes["otel.status_description"] = description

    def record_exception(self, exception: Exception) -> None:
        self.attributes["exception.type"] = type(exception).__name__
        self.attributes["exception.message"] = str(exception)

    def end(self) -> None:
        self.end_time = time.monotonic()


class StrataTelemetry:
    """Telemetry coordinator for tracing experiment runs, faults, and throughput."""

    def __init__(
        self,
        enabled: bool = False,
        in_memory: bool = False,
        service_name: str = "strata-framework",
    ) -> None:
        self.enabled = enabled
        self.in_memory = in_memory
        self.service_name = service_name
        self._spans: list[dict[str, Any]] = []
        self._counters: dict[str, int] = {}
        self._histograms: dict[str, list[float]] = {}

        # Attempt to link real opentelemetry if available and enabled
        self._real_tracer = None
        self._real_meter = None
        if self.enabled:
            try:
                from opentelemetry import trace, metrics
                self._real_tracer = trace.get_tracer(self.service_name)
                self._real_meter = metrics.get_meter(self.service_name)
            except ImportError:
                pass

    @contextmanager
    def trace_span(
        self,
        name: str,
        attributes: Mapping[str, Any] | None = None,
    ) -> Generator[NoOpSpan, None, None]:
        """Create a tracing span around a critical execution block."""
        span = NoOpSpan(name=name, attributes=dict(attributes or {}))
        start_ns = time.time_ns()
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            raise exc
        finally:
            span.end()
            duration_us = (time.time_ns() - start_ns) // 1000
            span.set_attribute("duration_us", duration_us)
            if self.enabled and self.in_memory:
                self._spans.append({
                    "name": span.name,
                    "attributes": dict(span.attributes),
                    "duration_us": duration_us,
                })

    def record_counter(
        self,
        name: str,
        value: int = 1,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Increment a metric counter."""
        if not self.enabled:
            return
        if self.in_memory:
            self._counters[name] = self._counters.get(name, 0) + value

    def record_histogram(
        self,
        name: str,
        value: float,
        attributes: Mapping[str, Any] | None = None,
    ) -> None:
        """Record a numerical value in a histogram distribution."""
        if not self.enabled:
            return
        if self.in_memory:
            if name not in self._histograms:
                self._histograms[name] = []
            self._histograms[name].append(float(value))

    def get_in_memory_records(self) -> dict[str, Any]:
        """Return captured in-memory spans and metrics."""
        return {
            "spans": list(self._spans),
            "counters": dict(self._counters),
            "histograms": dict(self._histograms),
        }

    def clear(self) -> None:
        """Clear captured in-memory telemetry records."""
        self._spans.clear()
        self._counters.clear()
        self._histograms.clear()


# Global telemetry singleton
_GLOBAL_TELEMETRY: StrataTelemetry | None = None


def get_telemetry() -> StrataTelemetry:
    """Retrieve the global Strata telemetry instance."""
    global _GLOBAL_TELEMETRY
    if _GLOBAL_TELEMETRY is None:
        _GLOBAL_TELEMETRY = StrataTelemetry(enabled=False)
    return _GLOBAL_TELEMETRY


def configure_telemetry(
    enabled: bool = False,
    in_memory: bool = False,
) -> StrataTelemetry:
    """Configure and set the global telemetry instance."""
    global _GLOBAL_TELEMETRY
    _GLOBAL_TELEMETRY = StrataTelemetry(enabled=enabled, in_memory=in_memory)
    return _GLOBAL_TELEMETRY
