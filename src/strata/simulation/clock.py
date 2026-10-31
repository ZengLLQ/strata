"""Virtual discrete-event clock implementation."""

from __future__ import annotations

from strata.core.errors import SimulationError
from strata.core.types import VirtualMicroseconds


class VirtualClock:
    """Monotonically advancing virtual clock measured in integer microseconds.
    
    The virtual clock never moves backward and only advances to the timestamp
    of dispatched discrete events.
    """

    def __init__(self, initial_time_us: VirtualMicroseconds = 0) -> None:
        if initial_time_us < 0:
            raise ValueError(f"Initial virtual time must be non-negative, got {initial_time_us}")
        self._current_time_us: VirtualMicroseconds = initial_time_us

    @property
    def current_time_us(self) -> VirtualMicroseconds:
        """Return the current virtual time in microseconds."""
        return self._current_time_us

    def advance_to(self, target_time_us: VirtualMicroseconds) -> None:
        """Advance the clock to target_time_us.
        
        Raises SimulationError if an attempt is made to move backward in time.
        """
        if target_time_us < self._current_time_us:
            raise SimulationError(
                f"Cannot advance virtual clock backwards from {self._current_time_us}us to {target_time_us}us"
            )
        self._current_time_us = target_time_us

    def reset(self, initial_time_us: VirtualMicroseconds = 0) -> None:
        """Reset the clock back to the initial timestamp."""
        if initial_time_us < 0:
            raise ValueError(f"Initial virtual time must be non-negative, got {initial_time_us}")
        self._current_time_us = initial_time_us

    def __repr__(self) -> str:
        return f"<VirtualClock current_time_us={self._current_time_us}>"
