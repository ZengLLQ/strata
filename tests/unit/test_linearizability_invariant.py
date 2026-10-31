"""Unit tests for LinearizableKVInvariant evaluating experiment histories."""

from __future__ import annotations

import pytest

from strata.core.types import InvariantVerdict
from strata.invariants.linearizability import LinearizableKVInvariant
from strata.invariants.registry import InvariantRegistry
from strata.simulation.events import WorkloadOperationEvent


class DummyEngine:
    """Mock engine for invariant evaluation."""
    def __init__(self, experiment: object = None) -> None:
        self.experiment = experiment


def test_linearizability_invariant_registration() -> None:
    """Verify invariant is registered in InvariantRegistry."""
    inv = InvariantRegistry.create("linearizability", "inv_lin", "Linearizability check")
    assert isinstance(inv, LinearizableKVInvariant)
    assert inv.invariant_id == "inv_lin"
    assert inv.invariant_type == "linearizability"


def test_linearizability_invariant_empty_events() -> None:
    """Zero workload operations returns INCONCLUSIVE verdict."""
    inv = LinearizableKVInvariant()
    res = inv.evaluate(DummyEngine(), [])
    assert res.verdict == InvariantVerdict.INCONCLUSIVE
    assert "No client operations" in res.explanation


def test_linearizability_invariant_valid_kv_history() -> None:
    """Valid put and get operations evaluate to PASSED."""
    events = [
        WorkloadOperationEvent.create(
            sequence_id=1,
            timestamp_us=1000,
            target_node="node-1",
            operation_id="op_1",
            op_type="put",
            key="k1",
            value="v1",
            extra={"return_time_us": 2000, "status_code": 200},
        ),
        WorkloadOperationEvent.create(
            sequence_id=2,
            timestamp_us=3000,
            target_node="node-1",
            operation_id="op_2",
            op_type="get",
            key="k1",
            value="v1",
            extra={"return_time_us": 4000, "status_code": 200},
        ),
    ]

    inv = LinearizableKVInvariant()
    res = inv.evaluate(DummyEngine(), events)
    assert res.verdict == InvariantVerdict.PASSED
    assert len(res.details["linearized_sequence"]) == 2


def test_linearizability_invariant_stale_read_violation() -> None:
    """Stale read returning old value after write completed returns VIOLATED."""
    events = [
        WorkloadOperationEvent.create(
            sequence_id=1,
            timestamp_us=1000,
            target_node="node-1",
            operation_id="w_1",
            op_type="put",
            key="k1",
            value="v_new",
            extra={"return_time_us": 2000, "status_code": 200},
        ),
        WorkloadOperationEvent.create(
            sequence_id=2,
            timestamp_us=3000,
            target_node="node-2",
            operation_id="r_2",
            op_type="get",
            key="k1",
            value=None,  # Stale! Missed the committed write
            extra={"return_time_us": 4000, "status_code": 200},
        ),
    ]

    inv = LinearizableKVInvariant()
    res = inv.evaluate(DummyEngine(), events)
    assert res.verdict == InvariantVerdict.VIOLATED
    assert "non-linearizable" in res.explanation.lower()
