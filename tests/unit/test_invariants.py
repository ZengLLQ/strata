"""Unit tests for invariant evaluation."""

from strata.core.types import EventPriority, InvariantVerdict, NodeState
from strata.invariants.convergence import (
    FaultObservedInvariant,
    NoPanicInvariant,
    StateConvergenceInvariant,
)
from strata.simulation.events import BaseEvent, FaultAppliedEvent


class MockNode:
    def __init__(self, node_id: str, state: NodeState, store_data: dict) -> None:
        self.node_id = node_id
        self.state = state
        self._store = store_data

    def get_state_snapshot(self) -> dict:
        return self._store


class MockFault:
    def __init__(self, fault_id: str) -> None:
        self.id = fault_id


class MockEngine:
    def __init__(self, nodes: dict, fault_ids: list[str]) -> None:
        self.nodes = nodes
        self.experiment = type("Exp", (), {"faults": [MockFault(fid) for fid in fault_ids]})()


def test_state_convergence_invariant_passes() -> None:
    nodes = {
        "n1": MockNode("n1", NodeState.ONLINE, {"k1": "v1"}),
        "n2": MockNode("n2", NodeState.ONLINE, {"k1": "v1"}),
        "n3": MockNode("n3", NodeState.OFFLINE, {}),  # Crashed node excluded
    }
    engine = MockEngine(nodes, [])
    inv = StateConvergenceInvariant()

    result = inv.evaluate(engine, [])
    assert result.verdict == InvariantVerdict.PASSED
    assert "converged to identical state" in result.explanation


def test_state_convergence_invariant_violated() -> None:
    nodes = {
        "n1": MockNode("n1", NodeState.ONLINE, {"k1": "v1"}),
        "n2": MockNode("n2", NodeState.ONLINE, {"k1": "v2_divergent"}),
    }
    engine = MockEngine(nodes, [])
    inv = StateConvergenceInvariant()

    result = inv.evaluate(engine, [])
    assert result.verdict == InvariantVerdict.VIOLATED
    assert "divergence detected" in result.explanation.lower()


def test_fault_observed_invariant() -> None:
    engine = MockEngine({}, ["crash_1", "crash_2"])
    inv = FaultObservedInvariant()

    # Case 1: only crash_1 was applied
    events = [
        FaultAppliedEvent.create(
            sequence_id=1,
            timestamp_us=1000,
            fault_id="crash_1",
            fault_type="node_crash",
            target="n1",
            evidence={},
        )
    ]
    res_violated = inv.evaluate(engine, events)
    assert res_violated.verdict == InvariantVerdict.VIOLATED
    assert "crash_2" in res_violated.explanation

    # Case 2: both crash_1 and crash_2 applied
    events.append(
        FaultAppliedEvent.create(
            sequence_id=2,
            timestamp_us=2000,
            fault_id="crash_2",
            fault_type="node_crash",
            target="n2",
            evidence={},
        )
    )
    res_passed = inv.evaluate(engine, events)
    assert res_passed.verdict == InvariantVerdict.PASSED


def test_no_panic_invariant() -> None:
    engine = MockEngine({}, [])
    inv = NoPanicInvariant()

    clean_events = [
        BaseEvent(sequence_id=1, timestamp_us=100, priority=EventPriority.WORKLOAD_INGESTION, event_type="workload.op")
    ]
    assert inv.evaluate(engine, clean_events).verdict == InvariantVerdict.PASSED

    panic_events = clean_events + [
        BaseEvent(sequence_id=2, timestamp_us=200, priority=EventPriority.SYSTEM_FAULT, event_type="engine.error")
    ]
    assert inv.evaluate(engine, panic_events).verdict == InvariantVerdict.VIOLATED
