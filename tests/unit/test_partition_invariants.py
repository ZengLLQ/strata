"""Unit tests for the PartitionIsolationInvariant."""

from strata.core.types import EventPriority, InvariantVerdict
from strata.invariants.convergence import PartitionIsolationInvariant
from strata.simulation.events import BaseEvent, FaultAppliedEvent, MessageDeliveryEvent


def test_partition_isolation_passes_when_no_cross_messages() -> None:
    inv = PartitionIsolationInvariant()

    events = [
        # Partition starts at 10,000us between {n1} and {n2}
        FaultAppliedEvent.create(
            sequence_id=1,
            timestamp_us=10000,
            fault_id="p1",
            fault_type="network_partition",
            target="net",
            evidence={"group_a": ["n1"], "group_b": ["n2"]},
        ),
        # Message within group at 12,000us
        MessageDeliveryEvent.create(
            sequence_id=2,
            timestamp_us=12000,
            source="n1",
            target="n1",
            message_type="local",
            data={},
        ),
        # Heal at 20,000us
        FaultAppliedEvent.create(
            sequence_id=3,
            timestamp_us=20000,
            fault_id="p1_heal",
            fault_type="network_heal",
            target="net",
            evidence={"healed_group_a": ["n1"], "healed_group_b": ["n2"]},
        ),
        # Message after heal at 25,000us
        MessageDeliveryEvent.create(
            sequence_id=4,
            timestamp_us=25000,
            source="n1",
            target="n2",
            message_type="replicate",
            data={},
        ),
    ]

    result = inv.evaluate(engine=None, events=events)
    assert result.verdict == InvariantVerdict.PASSED


def test_partition_isolation_violated_when_message_crosses() -> None:
    inv = PartitionIsolationInvariant()

    events = [
        FaultAppliedEvent.create(
            sequence_id=1,
            timestamp_us=10000,
            fault_id="p1",
            fault_type="network_partition",
            target="net",
            evidence={"group_a": ["n1"], "group_b": ["n2"]},
        ),
        # Violating delivery during active partition window (t=15,000us)
        MessageDeliveryEvent.create(
            sequence_id=2,
            timestamp_us=15000,
            source="n1",
            target="n2",
            message_type="leak",
            data={},
        ),
        FaultAppliedEvent.create(
            sequence_id=3,
            timestamp_us=20000,
            fault_id="p1_heal",
            fault_type="network_heal",
            target="net",
            evidence={"healed_group_a": ["n1"], "healed_group_b": ["n2"]},
        ),
    ]

    result = inv.evaluate(engine=None, events=events)
    assert result.verdict == InvariantVerdict.VIOLATED
    assert result.relevant_event_ids == [2]
    assert "Partition isolation violated" in result.explanation
