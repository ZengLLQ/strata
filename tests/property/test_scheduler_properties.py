"""Property-based tests for deterministic scheduler ordering using Hypothesis."""

from hypothesis import given, strategies as st
from strata.core.types import EventPriority
from strata.simulation.events import BaseEvent
from strata.simulation.queue import PriorityEventQueue


@st.composite
def event_strategy(draw: st.DrawFn) -> BaseEvent:
    timestamp_us = draw(st.integers(min_value=0, max_value=1_000_000))
    priority = draw(st.sampled_from(list(EventPriority)))
    sequence_id = draw(st.integers(min_value=0, max_value=10_000))
    event_type = draw(st.text(min_size=1, max_size=10))
    return BaseEvent(
        sequence_id=sequence_id,
        timestamp_us=timestamp_us,
        priority=priority,
        event_type=event_type,
    )


@given(st.lists(event_strategy(), min_size=1, max_size=100))
def test_property_popped_events_strictly_monotonic_in_total_order(events: list[BaseEvent]) -> None:
    """Property: For any collection of events, popped order must satisfy the total order key:
    
    (timestamp_us, priority, sequence_id)
    """
    queue = PriorityEventQueue()
    for e in events:
        queue.push(e)

    popped = [queue.pop() for _ in range(len(events))]

    for i in range(len(popped) - 1):
        curr = popped[i]
        nxt = popped[i + 1]

        # Monotonic timestamp
        assert curr.timestamp_us <= nxt.timestamp_us

        # If timestamps match, priority tier must not decrease
        if curr.timestamp_us == nxt.timestamp_us:
            assert int(curr.priority) <= int(nxt.priority)

            # If timestamp and priority match, sequence_id must not decrease
            if curr.priority == nxt.priority:
                assert curr.sequence_id <= nxt.sequence_id
