"""Unit tests for the PriorityEventQueue and deterministic scheduler contract."""

import pytest
from strata.core.types import EventPriority
from strata.simulation.events import BaseEvent
from strata.simulation.queue import PriorityEventQueue


def test_queue_orders_by_timestamp_first() -> None:
    queue = PriorityEventQueue()

    e1 = BaseEvent(sequence_id=1, timestamp_us=500, priority=EventPriority.WORKLOAD_INGESTION, event_type="e1")
    e2 = BaseEvent(sequence_id=2, timestamp_us=100, priority=EventPriority.WORKLOAD_INGESTION, event_type="e2")
    e3 = BaseEvent(sequence_id=3, timestamp_us=300, priority=EventPriority.WORKLOAD_INGESTION, event_type="e3")

    queue.push(e1)
    queue.push(e2)
    queue.push(e3)

    assert queue.pop().event_type == "e2"
    assert queue.pop().event_type == "e3"
    assert queue.pop().event_type == "e1"


def test_queue_orders_by_priority_tier_on_identical_timestamp() -> None:
    queue = PriorityEventQueue()

    e_workload = BaseEvent(sequence_id=1, timestamp_us=200, priority=EventPriority.WORKLOAD_INGESTION, event_type="workload")
    e_fault = BaseEvent(sequence_id=2, timestamp_us=200, priority=EventPriority.SYSTEM_FAULT, event_type="fault")
    e_network = BaseEvent(sequence_id=3, timestamp_us=200, priority=EventPriority.NETWORK_DELIVERY, event_type="network")

    queue.push(e_workload)
    queue.push(e_fault)
    queue.push(e_network)

    # Expected order: fault (0) -> network (2) -> workload (3)
    assert queue.pop().event_type == "fault"
    assert queue.pop().event_type == "network"
    assert queue.pop().event_type == "workload"


def test_queue_orders_by_sequence_id_on_identical_timestamp_and_priority() -> None:
    queue = PriorityEventQueue()

    e_first = BaseEvent(sequence_id=10, timestamp_us=1000, priority=EventPriority.NETWORK_DELIVERY, event_type="first")
    e_second = BaseEvent(sequence_id=11, timestamp_us=1000, priority=EventPriority.NETWORK_DELIVERY, event_type="second")
    e_third = BaseEvent(sequence_id=12, timestamp_us=1000, priority=EventPriority.NETWORK_DELIVERY, event_type="third")

    # Insert out of order
    queue.push(e_third)
    queue.push(e_first)
    queue.push(e_second)

    assert queue.pop().sequence_id == 10
    assert queue.pop().sequence_id == 11
    assert queue.pop().sequence_id == 12


def test_queue_peek_and_empty() -> None:
    queue = PriorityEventQueue()
    assert queue.peek() is None
    assert len(queue) == 0
    assert not queue

    e = BaseEvent(sequence_id=1, timestamp_us=10, priority=EventPriority.SYSTEM_FAULT, event_type="test")
    queue.push(e)

    assert queue.peek() is not None
    assert queue.peek().sequence_id == 1
    assert len(queue) == 1
    assert bool(queue)

    popped = queue.pop()
    assert popped.sequence_id == 1
    assert len(queue) == 0

    with pytest.raises(IndexError):
        queue.pop()
