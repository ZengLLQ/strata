"""Deterministic priority event queue with strict total ordering."""

from __future__ import annotations

import heapq
from typing import Iterator

from strata.core.errors import SimulationError
from strata.core.types import EventPriority, EventSequenceId, VirtualMicroseconds
from strata.simulation.events import BaseEvent


class PriorityEventQueue:
    """Deterministic event queue using a min-heap with an explicit 3-tuple total order key:
    
    (timestamp_us, priority, sequence_id).
    
    This guarantees that events with identical timestamps and priorities are dispatched
    in the deterministic order of their creation (sequence_id), eliminating non-deterministic
    tie-breaking drift.
    """

    def __init__(self) -> None:
        # Heap elements: (timestamp_us, priority, sequence_id, event)
        self._heap: list[tuple[VirtualMicroseconds, EventPriority, EventSequenceId, BaseEvent]] = []
        self._last_popped_time: VirtualMicroseconds = 0

    def push(self, event: BaseEvent) -> None:
        """Add an event to the priority queue."""
        entry = (event.timestamp_us, event.priority, event.sequence_id, event)
        heapq.heappush(self._heap, entry)

    def pop(self) -> BaseEvent:
        """Pop and return the earliest scheduled event according to the total ordering contract.
        
        Raises IndexError if the queue is empty.
        Raises SimulationError if an event with a retrogressive timestamp is encountered.
        """
        if not self._heap:
            raise IndexError("pop from empty event queue")
        
        timestamp_us, _, _, event = heapq.heappop(self._heap)
        if timestamp_us < self._last_popped_time:
            raise SimulationError(
                f"Scheduler contract violation: popped event with timestamp {timestamp_us}us "
                f"which is earlier than previous event timestamp {self._last_popped_time}us"
            )
        self._last_popped_time = timestamp_us
        return event

    def peek(self) -> BaseEvent | None:
        """Inspect the next event without removing it, or return None if empty."""
        if not self._heap:
            return None
        return self._heap[0][3]

    def __len__(self) -> int:
        return len(self._heap)

    def __bool__(self) -> bool:
        return bool(self._heap)

    def clear(self) -> None:
        """Clear all pending events."""
        self._heap.clear()
        self._last_popped_time = 0

    def __iter__(self) -> Iterator[BaseEvent]:
        """Iterate over all remaining events in priority order (consuming the queue)."""
        while self:
            yield self.pop()
