"""Unit tests for BaseServiceAdapter and ServiceAdapterContract."""

from __future__ import annotations

import pytest

from strata.adapters.base import BaseServiceAdapter
from strata.core.contracts import EventContract, ServiceAdapterContract
from strata.core.errors import DestructiveActionRefusalError


class DummyServiceAdapter(BaseServiceAdapter):
    """Minimal concrete implementation for testing base adapter behaviors."""

    @property
    def adapter_name(self) -> str:
        return "dummy"

    def setup(self, timeout_seconds: float = 30.0) -> None:
        pass

    def health_check(self, timeout_seconds: float = 5.0) -> bool:
        return True

    def execute_workload(self, workload_config: object, start_time_ns: int) -> list[EventContract]:
        return []

    def inject_fault(self, fault_config: object, now_ns: int) -> EventContract:
        raise NotImplementedError

    def collect_results(self) -> dict[str, object]:
        return {"node_states": {}}

    def teardown(self) -> None:
        pass


def test_base_adapter_contract_conformance() -> None:
    """Verify that concrete adapter conforms to ServiceAdapterContract protocol."""
    adapter = DummyServiceAdapter()
    assert isinstance(adapter, ServiceAdapterContract)
    assert adapter.adapter_name == "dummy"
    assert adapter.allow_destructive is False


def test_destructive_action_guardrails() -> None:
    """Verify that destructive operations are blocked by default and allowed when authorized."""
    safe_adapter = DummyServiceAdapter(allow_destructive=False)
    with pytest.raises(DestructiveActionRefusalError) as exc_info:
        safe_adapter.verify_destructive_allowed("kill_database_process")
    assert "kill_database_process" in str(exc_info.value)
    assert "disabled by default" in str(exc_info.value)

    # When explicitly authorized, verification passes without error
    auth_adapter = DummyServiceAdapter(allow_destructive=True)
    auth_adapter.verify_destructive_allowed("kill_database_process")


def test_environment_metadata_collection() -> None:
    """Verify that environment metadata contains required system descriptors."""
    adapter = DummyServiceAdapter()
    meta = adapter.get_environment_metadata()

    assert "os_name" in meta
    assert "os_version" in meta
    assert "python_version" in meta
    assert "python_implementation" in meta
    assert "architecture" in meta
    assert "cpu_count" in meta
    assert meta["cpu_count"] >= 1
    assert "hostname" in meta


def test_determinism_limitations_documentation() -> None:
    """Verify explicit documentation of non-deterministic real-system boundaries."""
    adapter = DummyServiceAdapter()
    limits = adapter.get_determinism_limitations()

    assert "repeatability" in limits
    assert "timing" in limits
    assert "fault_observability" in limits
    assert "network_semantics" in limits

    # Must explicitly state non-determinism
    assert "non-deterministic" in limits["repeatability"].lower()
    assert "wall-clock" in limits["timing"].lower()
