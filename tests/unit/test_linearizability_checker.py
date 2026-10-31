"""Unit tests for the LinearizabilityChecker state exploration algorithm."""

from __future__ import annotations

import pytest

from strata.invariants.linearizability import (
    LinearizabilityChecker,
    OperationRecord,
    SequentialKV,
    SequentialRegister,
)


def test_linearizable_sequential_history() -> None:
    """Strictly sequential operations are linearizable."""
    ops = [
        OperationRecord(client_id="c1", op_id="1", op_type="write", input_val=10, output_val="ok", invoke_time_us=100, return_time_us=200),
        OperationRecord(client_id="c2", op_id="2", op_type="read", input_val=None, output_val=10, invoke_time_us=300, return_time_us=400),
        OperationRecord(client_id="c1", op_id="3", op_type="write", input_val=20, output_val="ok", invoke_time_us=500, return_time_us=600),
        OperationRecord(client_id="c2", op_id="4", op_type="read", input_val=None, output_val=20, invoke_time_us=700, return_time_us=800),
    ]

    checker = LinearizabilityChecker(model=SequentialRegister())
    res = checker.check(ops)

    assert res.is_linearizable is True
    assert len(res.linearized_sequence) == 4
    assert [op.op_id for op in res.linearized_sequence] == ["1", "2", "3", "4"]


def test_linearizable_overlapping_concurrent_writes() -> None:
    """Two concurrent writes overlapping in time can be linearized in either order matching observations."""
    # Write 1: [100, 500] (val=1)
    # Write 2: [150, 450] (val=2)
    # Read 3:  [600, 700] observes 2
    ops = [
        OperationRecord(client_id="c1", op_id="w1", op_type="write", input_val=1, output_val="ok", invoke_time_us=100, return_time_us=500),
        OperationRecord(client_id="c2", op_id="w2", op_type="write", input_val=2, output_val="ok", invoke_time_us=150, return_time_us=450),
        OperationRecord(client_id="c3", op_id="r3", op_type="read", input_val=None, output_val=2, invoke_time_us=600, return_time_us=700),
    ]

    checker = LinearizabilityChecker(model=SequentialRegister())
    res = checker.check(ops)

    assert res.is_linearizable is True
    # Legal linearization: w1 happened first, then w2 overwrote it, then r3 saw 2
    assert [op.op_id for op in res.linearized_sequence] == ["w1", "w2", "r3"]


def test_non_linearizable_stale_read() -> None:
    """Reading a stale value after a write has completely returned violates linearizability."""
    # Write 1 finishes at t=200
    # Read 2 starts at t=300 (strictly after Write 1 returned!) but returns initial None/0
    ops = [
        OperationRecord(client_id="c1", op_id="w1", op_type="write", input_val=42, output_val="ok", invoke_time_us=100, return_time_us=200),
        OperationRecord(client_id="c2", op_id="r2", op_type="read", input_val=None, output_val=None, invoke_time_us=300, return_time_us=400),
    ]

    checker = LinearizabilityChecker(model=SequentialRegister(initial_value=None))
    res = checker.check(ops)

    assert res.is_linearizable is False
    assert res.linearized_sequence == []
    assert "r2" in res.explanation


def test_non_linearizable_backward_read_anomaly() -> None:
    """Read observing newer value followed by non-overlapping read observing older value violates linearizability."""
    # Concurrent writes: W(1) and W(2) overlapping [100, 300]
    # R1: [400, 500] reads 2 -> establishes that W(2) linearized after W(1)
    # R2: [600, 700] reads 1 -> impossible if W(2) already took effect!
    ops = [
        OperationRecord(client_id="c1", op_id="w1", op_type="write", input_val=1, output_val="ok", invoke_time_us=100, return_time_us=300),
        OperationRecord(client_id="c2", op_id="w2", op_type="write", input_val=2, output_val="ok", invoke_time_us=100, return_time_us=300),
        OperationRecord(client_id="c3", op_id="r1", op_type="read", input_val=None, output_val=2, invoke_time_us=400, return_time_us=500),
        OperationRecord(client_id="c4", op_id="r2", op_type="read", input_val=None, output_val=1, invoke_time_us=600, return_time_us=700),
    ]

    checker = LinearizabilityChecker(model=SequentialRegister())
    res = checker.check(ops)

    assert res.is_linearizable is False


def test_linearizable_kv_multi_key_partitioning() -> None:
    """KV operations on independent keys are partitioned and checked independently."""
    ops = [
        OperationRecord(client_id="c1", op_id="k1_w", op_type="put", input_val=("alpha", 10), output_val=10, invoke_time_us=100, return_time_us=200),
        OperationRecord(client_id="c2", op_id="k2_w", op_type="put", input_val=("beta", 20), output_val=20, invoke_time_us=150, return_time_us=250),
        OperationRecord(client_id="c1", op_id="k1_r", op_type="get", input_val=("alpha", None), output_val=10, invoke_time_us=300, return_time_us=400),
        OperationRecord(client_id="c2", op_id="k2_r", op_type="get", input_val=("beta", None), output_val=20, invoke_time_us=350, return_time_us=450),
    ]

    checker = LinearizabilityChecker(model=SequentialKV())
    res = checker.check(ops)

    assert res.is_linearizable is True
    assert len(res.linearized_sequence) == 4
