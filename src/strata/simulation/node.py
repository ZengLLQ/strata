"""Simulated node abstractions and reference replicated key-value implementation."""

from __future__ import annotations

from typing import Any, Mapping

from strata.core.errors import NodeStateError
from strata.core.types import NodeId, NodeState, VirtualMicroseconds


class BaseSimulatedNode:
    """Base class for all simulated nodes in Strata experiments."""

    def __init__(
        self,
        node_id: NodeId,
        role: str = "replica",
        initial_state: NodeState = NodeState.ONLINE,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        self.node_id = node_id
        self.role = role
        self._state = initial_state
        self.parameters = dict(parameters or {})
        self.crashed_at_us: VirtualMicroseconds | None = None
        self.recovered_at_us: VirtualMicroseconds | None = None
        self.clock_offset_us: int = 0
        self.clock_drift_ppm: float = 0.0
        self.drift_start_us: VirtualMicroseconds = 0

    @property
    def state(self) -> NodeState:
        """Current operational lifecycle state."""
        return self._state

    def is_online(self) -> bool:
        """Return True if the node is in ONLINE state."""
        return self._state == NodeState.ONLINE

    def initialize(self) -> None:
        """Lifecycle hook called when the simulation starts."""
        pass

    def get_perceived_time(self, now_us: VirtualMicroseconds) -> VirtualMicroseconds:
        """Return the node's perceived virtual time taking into account clock skew and drift."""
        offset = self.clock_offset_us
        if self.clock_drift_ppm != 0.0:
            elapsed = max(0, now_us - self.drift_start_us)
            drift_us = int(elapsed * (self.clock_drift_ppm / 1_000_000.0))
            offset += drift_us
        return max(0, now_us + offset)

    def set_clock_offset(self, offset_us: int) -> None:
        """Adjust the node's perceived clock offset in microseconds."""
        self.clock_offset_us = offset_us

    def set_clock_drift(self, drift_ppm: float, now_us: VirtualMicroseconds = 0) -> None:
        """Adjust the node's perceived clock drift in parts-per-million (ppm)."""
        self.clock_drift_ppm = float(drift_ppm)
        self.drift_start_us = now_us

    def set_clock_skew(
        self,
        offset_us: int = 0,
        drift_ppm: float = 0.0,
        now_us: VirtualMicroseconds = 0,
    ) -> None:
        """Configure both perceived clock offset and drift rate."""
        self.clock_offset_us = offset_us
        self.clock_drift_ppm = float(drift_ppm)
        self.drift_start_us = now_us

    def reset_clock_offset(self) -> None:
        """Reset the node's perceived clock offset and drift back to zero."""
        self.clock_offset_us = 0
        self.clock_drift_ppm = 0.0
        self.drift_start_us = 0

    def crash(self, now_us: VirtualMicroseconds) -> None:
        """Crash the node, setting its state to OFFLINE."""
        if self._state == NodeState.OFFLINE:
            # Idempotent or already crashed
            return
        self._state = NodeState.OFFLINE
        self.crashed_at_us = now_us

    def recover(self, now_us: VirtualMicroseconds) -> None:
        """Recover the node from crash, returning to ONLINE state."""
        self._state = NodeState.ONLINE
        self.recovered_at_us = now_us

    def handle_message(
        self,
        sender: NodeId,
        message_type: str,
        payload: Mapping[str, Any],
        now_us: VirtualMicroseconds,
    ) -> list[tuple[NodeId, str, dict[str, Any]]]:
        """Process an incoming message.
        
        Returns a list of outbound messages: [(target_node, message_type, payload_dict), ...]
        If the node is offline, this is a no-op returning an empty list.
        """
        if not self.is_online():
            return []
        return self._process_message(sender, message_type, payload, now_us)

    def _process_message(
        self,
        sender: NodeId,
        message_type: str,
        payload: Mapping[str, Any],
        now_us: VirtualMicroseconds,
    ) -> list[tuple[NodeId, str, dict[str, Any]]]:
        """Subclass implementation of message handling."""
        return []


class ReplicatedKVNode(BaseSimulatedNode):
    """Reference replicated key-value store node for 3-node cluster experiments.
    
    Supports:
    - Client 'client_write' (key, value):
        Updates local store and broadcasts 'replicate_request' to peer nodes.
    - Peer 'replicate_request' (key, value, version):
        Replicates state if version is newer, sends 'replicate_ack' back.
    - Peer 'replicate_ack' (key, version):
        Acknowledges receipt of replication.
    """

    def __init__(
        self,
        node_id: NodeId,
        peers: list[NodeId],
        role: str = "replica",
        initial_state: NodeState = NodeState.ONLINE,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(node_id, role, initial_state, parameters)
        self.peers = [p for p in peers if p != node_id]
        # In-memory key-value state: key -> (value, version)
        self.store: dict[str, tuple[Any, int]] = {}
        # Replication tracking: (key, version) -> set of acknowledging nodes
        self.replication_acks: dict[tuple[str, int], set[NodeId]] = {}
        # Operational counters
        self.writes_received: int = 0
        self.replications_applied: int = 0

    def _process_message(
        self,
        sender: NodeId,
        message_type: str,
        payload: Mapping[str, Any],
        now_us: VirtualMicroseconds,
    ) -> list[tuple[NodeId, str, dict[str, Any]]]:
        outbound: list[tuple[NodeId, str, dict[str, Any]]] = []

        if message_type == "client_write":
            key = str(payload["key"])
            value = payload["value"]
            self.writes_received += 1

            # Increment local version
            _, current_ver = self.store.get(key, (None, 0))
            new_ver = current_ver + 1
            self.store[key] = (value, new_ver)

            # Initialize acks tracking with local node
            self.replication_acks[(key, new_ver)] = {self.node_id}

            # Broadcast replicate_request to all peers
            for peer in self.peers:
                outbound.append((
                    peer,
                    "replicate_request",
                    {
                        "key": key,
                        "value": value,
                        "version": new_ver,
                        "origin": self.node_id,
                    },
                ))

        elif message_type == "replicate_request":
            key = str(payload["key"])
            value = payload["value"]
            incoming_ver = int(payload["version"])

            _, current_ver = self.store.get(key, (None, 0))
            if incoming_ver > current_ver:
                self.store[key] = (value, incoming_ver)
                self.replications_applied += 1

            # Send ack back to origin
            outbound.append((
                sender,
                "replicate_ack",
                {"key": key, "version": incoming_ver, "replica": self.node_id},
            ))

        elif message_type == "replicate_ack":
            key = str(payload["key"])
            ver = int(payload["version"])
            ack_node = str(payload["replica"])

            if (key, ver) in self.replication_acks:
                self.replication_acks[(key, ver)].add(ack_node)

        return outbound

    def get_state_snapshot(self) -> dict[str, Any]:
        """Return a clean dictionary snapshot of current key-value state."""
        return {k: v[0] for k, v in self.store.items()}
