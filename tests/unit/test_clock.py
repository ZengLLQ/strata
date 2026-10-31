"""Unit tests for the VirtualClock."""

import pytest
from strata.core.errors import SimulationError
from strata.simulation.clock import VirtualClock


def test_clock_initialization() -> None:
    clock = VirtualClock()
    assert clock.current_time_us == 0

    clock_custom = VirtualClock(1000)
    assert clock_custom.current_time_us == 1000


def test_clock_rejects_negative_time() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        VirtualClock(-50)


def test_clock_advances_monotonically() -> None:
    clock = VirtualClock(100)
    clock.advance_to(150)
    assert clock.current_time_us == 150

    clock.advance_to(150)  # Same timestamp is valid
    assert clock.current_time_us == 150

    clock.advance_to(500)
    assert clock.current_time_us == 500


def test_clock_rejects_backward_advance() -> None:
    clock = VirtualClock(200)
    with pytest.raises(SimulationError, match="backwards"):
        clock.advance_to(199)


def test_clock_reset() -> None:
    clock = VirtualClock(500)
    clock.reset(0)
    assert clock.current_time_us == 0

    with pytest.raises(ValueError, match="non-negative"):
        clock.reset(-1)
