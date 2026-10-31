"""Unit tests for network partition, healing, message drop, and delay faults."""

import random
from strata.core.experiment import NetworkConfig
from strata.core.types import FaultPhase
from strata.faults.network import (
    MessageDelayFault,
    MessageDropFault,
    NetworkHealFault,
    NetworkPartitionFault,
)
from strata.simulation.engine import DeterministicSimulationEngine
from strata.simulation.network import MessageDelayRule, MessageDropRule, SimulatedNetwork


def test_network_partition_and_healing() -> None:
    net = SimulatedNetwork(
        config=NetworkConfig(default_latency_us=1000, default_jitter_us=0),
        valid_nodes={"n1", "n2", "n3"},
        rng=random.Random(42),
    )

    # Initially communication is intact
    deliverable, _, status = net.calculate_delivery("n1", "n3", current_time_us=1000)
    assert deliverable is True
    assert status == "delivered"

    # Add partition: {n1, n2} vs {n3}
    net.add_partition({"n1", "n2"}, {"n3"})
    assert net.is_partitioned("n1", "n3")
    assert net.is_partitioned("n3", "n1")
    assert net.is_partitioned("n2", "n3")
    assert not net.is_partitioned("n1", "n2")  # intra-group remains unpartitioned

    # Message across partition must be dropped
    deliverable, _, status = net.calculate_delivery("n1", "n3", current_time_us=2000)
    assert deliverable is False
    assert status == "network_partition"

    # Message within group succeeds
    deliverable, _, status = net.calculate_delivery("n1", "n2", current_time_us=2000)
    assert deliverable is True

    # Heal partition
    net.remove_partition({"n1", "n2"}, {"n3"})
    assert not net.is_partitioned("n1", "n3")

    deliverable, _, status = net.calculate_delivery("n1", "n3", current_time_us=3000)
    assert deliverable is True
    assert status == "delivered"


def test_message_drop_rule_window() -> None:
    rule = MessageDropRule(
        rule_id="drop_test",
        source="n1",
        target="n2",
        message_type="replicate",
        start_time_us=10000,
        end_time_us=20000,
    )

    # Before window -> does not match
    assert not rule.matches("n1", "n2", "replicate", now_us=9999)

    # Inside window -> matches
    assert rule.matches("n1", "n2", "replicate", now_us=10000)
    assert rule.matches("n1", "n2", "replicate", now_us=15000)
    assert rule.matches("n1", "n2", "replicate", now_us=20000)

    # After window -> does not match
    assert not rule.matches("n1", "n2", "replicate", now_us=20001)

    # Mismatched source or target
    assert not rule.matches("n3", "n2", "replicate", now_us=15000)
    assert not rule.matches("n1", "n3", "replicate", now_us=15000)
    assert not rule.matches("n1", "n2", "client_write", now_us=15000)


def test_message_delay_rule_window() -> None:
    net = SimulatedNetwork(
        config=NetworkConfig(default_latency_us=1000, default_jitter_us=0),
        valid_nodes={"n1", "n2"},
        rng=random.Random(42),
    )

    delay_rule = MessageDelayRule(
        rule_id="delay_test",
        source="n1",
        target="n2",
        message_type="replicate",
        delay_us=5000,
        start_time_us=1000,
        end_time_us=5000,
    )
    net.add_delay_rule(delay_rule)

    # Outside window (t=500us): normal latency 1000us -> arrives at t=1500us
    deliverable, arrival_us, _ = net.calculate_delivery("n1", "n2", current_time_us=500, message_type="replicate")
    assert deliverable is True
    assert arrival_us == 1500

    # Inside window (t=2000us): 1000us + 5000us delay -> arrives at t=8000us
    deliverable, arrival_us, _ = net.calculate_delivery("n1", "n2", current_time_us=2000, message_type="replicate")
    assert deliverable is True
    assert arrival_us == 8000
