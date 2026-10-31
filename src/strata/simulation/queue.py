"""Deterministic priority event queue with strict total ordering."""

from __future__ import annotations

import heapq
from typing import Iterator

from strata.core.errors import SimulationError
from strata.core.types import EventPriority, EventSequenceId, VirtualMicroseconds
from strata.simulation.events import BaseEvent


class PriorityEventQueue:
    """Deterministic min-heap priority queue for discrete events.
    
    Total ordering contract:
    1. Virtual timestamp (timestamp_us): earlier events execute first.
    2. Priority tier (priority): lower integer values take precedence at identical times.
    3. Sequence ID (sequence_id): monotonic arrival ID breaks ties deterministically.
    
    Heap element: (timestamp_us, priority_int, sequence_id, event)
    """

    def __init__(self) -> None:
        self._heap: list[tuple[VirtualMicroseconds, int, EventSequenceId, BaseEvent]] = []

    def push(self, event: BaseEvent) -> None:
        """Push an event into the deterministic queue."""
        heap_item = (
            event.timestamp_us,
            int(event.priority),
            event.sequence_id,
            event,
        )
        heapq.heappush(self._heap, heap_item)

    def pop(self) -> BaseEvent:
        """Pop and return the next event according to total ordering."""
        if not self._heap:
            raise SimulationError("Cannot pop from an empty priority event queue.")
        _, _, _, event = heapq.heappop(self._heap)
        return event

    def peek(self) -> BaseEvent | None:
        """Return the next event without removing it, or None if empty."""
        if not self._heap:
            return None
        return self._heap[0][3]

    def clear(self) -> None:
        """Clear all events from the queue."""
        self._heap.clear()

    def __len__(self) -> int:
        return len(self._heap)

    def __bool__(self) -> bool:
        return bool(self._heap)

    def __iter__(self) -> Iterator[BaseEvent]:
        # Return events ordered by popping a copy of the heap
        copy_heap = list(self._heap)
        while copy_heap:
            yield heapq.heappop(copy_heap)[3]
