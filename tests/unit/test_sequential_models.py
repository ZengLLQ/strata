"""Unit tests for sequential specification models used in linearizability verification."""

from __future__ import annotations

import pytest

from strata.invariants.linearizability import (
    SequentialKV,
    SequentialRegister,
)


def test_sequential_register_basic() -> None:
    """SequentialRegister starts empty/none and tracks writes."""
    model = SequentialRegister(initial_value=None)
    state = model.initial_state()
    assert state == (None,)

    # Write 10
    valid, state, out = model.step(state, ("write", 10))
    assert valid is True
    assert state == (10,)
    assert out == "ok"

    # Read returns 10
    valid, state, out = model.step(state, ("read", None))
    assert valid is True
    assert state == (10,)
    assert out == 10

    # Overwrite with 20
    valid, state, out = model.step(state, ("write", 20))
    assert valid is True
    assert state == (20,)
    assert out == "ok"

    # Read returns 20
    valid, state, out = model.step(state, ("read", None))
    assert valid is True
    assert out == 20


def test_sequential_register_invalid_read() -> None:
    """Read expecting wrong value must return valid=False."""
    model = SequentialRegister(initial_value=0)
    state = model.initial_state()

    # If an operation claimed it read 99 when state was 0, it must fail validation
    valid, _, _ = model.step(state, ("read", None), expected_output=99)
    assert valid is False


def test_sequential_kv_operations() -> None:
    """SequentialKV handles put, get, and delete operations."""
    model = SequentialKV()
    state = model.initial_state()
    assert state == ()  # empty tuple representing immutable mapping

    # Put ("x", 1)
    valid, state, out = model.step(state, ("put", "x", 1))
    assert valid is True
    assert out == 1

    # Put ("y", 2)
    valid, state, out = model.step(state, ("put", "y", 2))
    assert valid is True
    assert out == 2

    # Get "x" -> 1
    valid, state, out = model.step(state, ("get", "x", None))
    assert valid is True
    assert out == 1

    # Get non-existent key "z" -> None
    valid, state, out = model.step(state, ("get", "z", None))
    assert valid is True
    assert out is None

    # Get expecting wrong output fails
    valid, _, _ = model.step(state, ("get", "x", None), expected_output=999)
    assert valid is False
