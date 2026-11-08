"""Unit tests for node lifecycle states and message handling."""

from strata.core.types import NodeState
from strata.simulation.node import BaseSimulatedNode, ReplicatedKVNode


def test_node_lifecycle_transitions() -> None:
    node = BaseSimulatedNode(node_id="node-1", role="replica", initial_state=NodeState.ONLINE)
    assert node.state == NodeState.ONLINE
    assert node.is_online()

    node.crash(now_us=1500)
    assert node.state == NodeState.OFFLINE
    assert not node.is_online()
    assert node.crashed_at_us == 1500

    node.recover(now_us=3000)
    assert node.state == NodeState.ONLINE
    assert node.is_online()
    assert node.recovered_at_us == 3000


def test_offline_node_drops_incoming_messages() -> None:
    node = ReplicatedKVNode(node_id="node-1", peers=["node-2", "node-3"])
    node.crash(now_us=100)

    # When offline, handle_message must return no outbound messages
    outbound = node.handle_message(
        sender="client",
        message_type="client_write",
        payload={"key": "k1", "value": "v1"},
        now_us=200,
    )
    assert outbound == []
    assert len(node.store) == 0


def test_replicated_kv_node_replication_flow() -> None:
    node1 = ReplicatedKVNode(node_id="node-1", peers=["node-2", "node-3"])
    node2 = ReplicatedKVNode(node_id="node-2", peers=["node-1", "node-3"])

    # 1. Node 1 receives client write
    outbound = node1.handle_message(
        sender="client",
        message_type="client_write",
        payload={"key": "k1", "value": "valA"},
        now_us=1000,
    )
    assert len(outbound) == 2  # Broadcasts to node-2 and node-3
    assert outbound[0][1] == "replicate_request"
    assert outbound[0][2]["key"] == "k1"
    assert outbound[0][2]["value"] == "valA"
    assert outbound[0][2]["version"] == 1

    # 2. Node 2 processes replicate request
    replicate_payload = outbound[0][2]
    outbound_node2 = node2.handle_message(
        sender="node-1",
        message_type="replicate_request",
        payload=replicate_payload,
        now_us=2000,
    )
    assert len(outbound_node2) == 1
    target, msg_type, ack_payload = outbound_node2[0]
    assert target == "node-1"
    assert msg_type == "replicate_ack"
    assert ack_payload["replica"] == "node-2"
    assert node2.get_state_snapshot() == {"k1": "valA"}
