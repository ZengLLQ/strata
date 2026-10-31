"""Base contracts and abstract class for external service integration adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
import os
import platform
import socket
import sys
from typing import Any, Sequence

from strata.core.contracts import EventContract, ServiceAdapterContract
from strata.core.errors import DestructiveActionRefusalError


class BaseServiceAdapter(ABC, ServiceAdapterContract):
    """Abstract base class for all real-system external service adapters.
    
    Provides standard environment metadata capture, determinism limitation documentation,
    and safety verification for destructive chaos operations.
    """

    def __init__(self, allow_destructive: bool = False) -> None:
        self.allow_destructive = allow_destructive

    @property
    @abstractmethod
    def adapter_name(self) -> str:
        """Distinguishable identifier for this adapter implementation."""
        ...

    @abstractmethod
    def setup(self, timeout_seconds: float = 30.0) -> None:
        """Initialize the integration environment and verify connectivity."""
        ...

    @abstractmethod
    def health_check(self, timeout_seconds: float = 5.0) -> bool:
        """Verify that all target services in the cluster are responsive."""
        ...

    @abstractmethod
    def execute_workload(
        self,
        workload_config: Any,
        start_time_ns: int,
    ) -> Sequence[EventContract]:
        """Execute a workload against target services and return observed event records."""
        ...

    @abstractmethod
    def inject_fault(
        self,
        fault_config: Any,
        now_ns: int,
    ) -> EventContract:
        """Apply a real-world fault to target external services and return evidence event."""
        ...

    @abstractmethod
    def collect_results(self) -> dict[str, Any]:
        """Gather final cluster state snapshots and metrics."""
        ...

    @abstractmethod
    def teardown(self) -> None:
        """Clean up all external integration resources and reset state."""
        ...

    def verify_destructive_allowed(self, action_description: str) -> None:
        """Verify that destructive operations are explicitly authorized.
        
        Raises DestructiveActionRefusalError if allow_destructive is False.
        """
        if not self.allow_destructive:
            raise DestructiveActionRefusalError(
                f"Destructive integration action '{action_description}' refused: "
                "destructive actions are disabled by default. "
                "Set 'allow_destructive: true' in execution configuration to authorize."
            )

    def get_environment_metadata(self) -> dict[str, Any]:
        """Gather host environment metadata for reproducibility and audit records."""
        hostname = "unknown"
        local_ip = "127.0.0.1"
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
        except Exception:
            pass

        return {
            "os_name": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "python_version": sys.version.split()[0],
            "python_implementation": platform.python_implementation(),
            "cpu_count": os.cpu_count() or 1,
            "hostname": hostname,
            "local_ip": local_ip,
        }

    def get_determinism_limitations(self) -> dict[str, str]:
        """Return explicit documentation of non-deterministic boundaries."""
        return {
            "repeatability": (
                "Real-system execution is non-deterministic. Operating system process scheduling, "
                "network stack buffering, socket congestion, and garbage collection introduce "
                "timing jitter across repeated runs."
            ),
            "timing": (
                "Timestamps are derived from host wall-clock time (nanoseconds converted to "
                "integer microseconds), not a discrete-event virtual clock."
            ),
            "fault_observability": (
                "Faults are observed via external HTTP responses, transport failures, and "
                "container health probes. Internal node memory and state transitions are "
                "not directly observable."
            ),
            "network_semantics": (
                "Network partitions in real systems rely on OS packet filtering or container "
                "network disconnection, which can have propagation delays and socket keepalive timeouts."
            ),
        }
