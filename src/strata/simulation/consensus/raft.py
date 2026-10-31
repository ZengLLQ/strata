"""Raft consensus state machine node implementation for discrete-event simulation."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from strata.core.types import NodeId, NodeState, VirtualMicroseconds
from strata.simulation.consensus.types import LogEntry, RaftRole
from strata.simulation.node import BaseSimulatedNode


class RaftNode(BaseSimulatedNode):
    """Simulated distributed node running the Raft consensus protocol.
    
    Implements leader election, heartbeat broadcasting, log replication,
    and committed state-machine application across crash and partition faults.
    """

    def __init__(
        self,
        node_id: NodeId,
        peers: Sequence[NodeId] | None = None,
        initial_state: NodeState = NodeState.ONLINE,
        election_timeout_us: int = 150000,
        heartbeat_interval_us: int = 50000,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(node_id=node_id, initial_state=initial_state, parameters=parameters)
        self.peers: list[NodeId] = list(peers or [])
        self.election_timeout_us = election_timeout_us
        self.heartbeat_interval_us = heartbeat_interval_us

        # Raft state
        self.role: RaftRole = RaftRole.FOLLOWER
        self.current_term: int = 0
        self.voted_for: NodeId | None = None

        # Log starts with dummy index 0
        self.log: list[LogEntry] = [LogEntry(index=0, term=0, command=("noop", "", None))]

        # Volatile state
        self.commit_index: int = 0
        self.last_applied: int = 0

        # Leader state
        self.next_index: dict[NodeId, int] = {}
        self.match_index: dict[NodeId, int] = {}
        self.votes_received: set[NodeId] = set()

        # Timers
        self.last_leader_contact_us: int = 0
        self.last_heartbeat_us: int = 0

        # State machine
        self.kv_store: dict[str, Any] = {}

    @property
    def total_nodes(self) -> int:
        return len(self.peers) + 1

    def check_timers(self, now_us: VirtualMicroseconds) -> list[tuple[NodeId, str, dict[str, Any]]]:
        """Check election and heartbeat timers, generating timer-driven RPCs."""
        if self.state != NodeState.ONLINE:
            return []

        outbound: list[tuple[NodeId, str, dict[str, Any]]] = []

        # 1. Leader heartbeats
        if self.role == RaftRole.LEADER:
            if now_us - self.last_heartbeat_us >= self.heartbeat_interval_us:
                self.last_heartbeat_us = now_us
                for peer in self.peers:
                    p_index = self.next_index.get(peer, len(self.log)) - 1
                    p_term = self.log[p_index].term if p_index < len(self.log) else 0
                    entries_to_send = [e.to_dict() for e in self.log[p_index + 1 :]]

                    outbound.append((
                        peer,
                        "AppendEntries",
                        {
                            "term": self.current_term,
                            "leader_id": self.node_id,
                            "prev_log_index": p_index,
                            "prev_log_term": p_term,
                            "entries": entries_to_send,
                            "leader_commit": self.commit_index,
                        },
                    ))
            return outbound

        # 2. Follower / Candidate election timeout
        if self.role in (RaftRole.FOLLOWER, RaftRole.CANDIDATE):
            if now_us - self.last_leader_contact_us >= self.election_timeout_us:
                # Start election
                self.role = RaftRole.CANDIDATE
                self.current_term += 1
                self.voted_for = self.node_id
                self.votes_received = {self.node_id}
                self.last_leader_contact_us = now_us

                last_idx = len(self.log) - 1
                last_term = self.log[last_idx].term

                for peer in self.peers:
                    outbound.append((
                        peer,
                        "RequestVote",
                        {
                            "term": self.current_term,
                            "candidate_id": self.node_id,
                            "last_log_index": last_idx,
                            "last_log_term": last_term,
                        },
                    ))

        return outbound

    def on_message(
        self,
        sender: NodeId,
        message_type: str,
        payload: Mapping[str, Any],
        now_us: VirtualMicroseconds,
    ) -> list[tuple[NodeId, str, dict[str, Any]]]:
        """Dispatch incoming messages to Raft consensus handlers."""
        if self.state != NodeState.ONLINE:
            return []

        msg_term = payload.get("term", 0)

        # Rule: If RPC request or response contains term T > current_term: set current_term = T, convert to follower
        if msg_term > self.current_term:
            self.current_term = msg_term
            self.role = RaftRole.FOLLOWER
            self.voted_for = None

        if message_type == "RequestVote":
            return self._handle_request_vote(sender, payload, now_us)
        elif message_type == "RequestVoteResponse":
            return self._handle_request_vote_response(sender, payload, now_us)
        elif message_type == "AppendEntries":
            return self._handle_append_entries(sender, payload, now_us)
        elif message_type == "AppendEntriesResponse":
            return self._handle_append_entries_response(sender, payload, now_us)
        elif message_type in ("ClientWrite", "client_write", "put", "write"):
            return self.handle_client_write(payload["key"], payload["value"], now_us)
        elif message_type in ("ClientRead", "client_read", "get", "read"):
            return []

        return []

    def _handle_request_vote(
        self,
        sender: NodeId,
        payload: Mapping[str, Any],
        now_us: VirtualMicroseconds,
    ) -> list[tuple[NodeId, str, dict[str, Any]]]:
        candidate_term = payload["term"]
        candidate_id = payload["candidate_id"]
        last_log_idx = payload.get("last_log_index", 0)
        last_log_term = payload.get("last_log_term", 0)

        vote_granted = False
        my_last_idx = len(self.log) - 1
        my_last_term = self.log[my_last_idx].term

        # Check term
        if candidate_term == self.current_term:
            if self.voted_for is None or self.voted_for == candidate_id:
                # Check if candidate's log is at least as up-to-date
                if (last_log_term > my_last_term) or (
                    last_log_term == my_last_term and last_log_idx >= my_last_idx
                ):
                    vote_granted = True
                    self.voted_for = candidate_id
                    self.last_leader_contact_us = now_us

        return [(
            sender,
            "RequestVoteResponse",
            {
                "term": self.current_term,
                "vote_granted": vote_granted,
                "voter_id": self.node_id,
            },
        )]

    def _handle_request_vote_response(
        self,
        sender: NodeId,
        payload: Mapping[str, Any],
        now_us: VirtualMicroseconds,
    ) -> list[tuple[NodeId, str, dict[str, Any]]]:
        if self.role != RaftRole.CANDIDATE:
            return []

        if payload.get("vote_granted") and payload.get("term") == self.current_term:
            self.votes_received.add(sender)
            # Check majority
            if len(self.votes_received) > self.total_nodes // 2:
                # Transition to Leader
                self.role = RaftRole.LEADER
                self.next_index = {p: len(self.log) for p in self.peers}
                self.match_index = {p: 0 for p in self.peers}
                self.match_index[self.node_id] = len(self.log) - 1
                self.last_heartbeat_us = now_us

                # Broadcast immediate initial heartbeats
                outbound: list[tuple[NodeId, str, dict[str, Any]]] = []
                for peer in self.peers:
                    last_idx = len(self.log) - 1
                    outbound.append((
                        peer,
                        "AppendEntries",
                        {
                            "term": self.current_term,
                            "leader_id": self.node_id,
                            "prev_log_index": last_idx,
                            "prev_log_term": self.log[last_idx].term,
                            "entries": [],
                            "leader_commit": self.commit_index,
                        },
                    ))
                return outbound

        return []

    def _handle_append_entries(
        self,
        sender: NodeId,
        payload: Mapping[str, Any],
        now_us: VirtualMicroseconds,
    ) -> list[tuple[NodeId, str, dict[str, Any]]]:
        term = payload["term"]
        prev_idx = payload["prev_log_index"]
        prev_term = payload["prev_log_term"]
        raw_entries = payload.get("entries", [])
        leader_commit = payload.get("leader_commit", 0)

        # 1. Reply false if term < current_term
        if term < self.current_term:
            return [(
                sender,
                "AppendEntriesResponse",
                {"term": self.current_term, "success": False, "match_index": len(self.log) - 1, "follower_id": self.node_id},
            )]

        # Valid leader contact
        self.role = RaftRole.FOLLOWER
        self.last_leader_contact_us = now_us

        # 2. Reply false if log doesn't contain an entry at prev_log_index matching prev_log_term
        if prev_idx >= len(self.log) or self.log[prev_idx].term != prev_term:
            return [(
                sender,
                "AppendEntriesResponse",
                {"term": self.current_term, "success": False, "match_index": min(prev_idx, len(self.log) - 1), "follower_id": self.node_id},
            )]

        # 3. If an existing entry conflicts with a new one, delete existing entry and all that follow it
        new_entries: list[LogEntry] = []
        for e in raw_entries:
            cmd = tuple(e["command"]) if isinstance(e["command"], list) else e["command"]
            new_entries.append(LogEntry(index=e["index"], term=e["term"], command=cmd))

        insert_idx = prev_idx + 1
        for entry in new_entries:
            if insert_idx < len(self.log):
                if self.log[insert_idx].term != entry.term:
                    self.log = self.log[:insert_idx]
                    self.log.append(entry)
            else:
                self.log.append(entry)
            insert_idx += 1

        # 4. If leader_commit > commit_index, set commit_index = min(leader_commit, index of last new entry)
        if leader_commit > self.commit_index:
            self.commit_index = min(leader_commit, len(self.log) - 1)
            self._apply_committed_entries()

        return [(
            sender,
            "AppendEntriesResponse",
            {"term": self.current_term, "success": True, "match_index": len(self.log) - 1, "follower_id": self.node_id},
        )]

    def _handle_append_entries_response(
        self,
        sender: NodeId,
        payload: Mapping[str, Any],
        now_us: VirtualMicroseconds,
    ) -> list[tuple[NodeId, str, dict[str, Any]]]:
        if self.role != RaftRole.LEADER:
            return []

        if payload.get("term") != self.current_term:
            return []

        success = payload.get("success", False)
        match_idx = payload.get("match_index", 0)

        if success:
            self.match_index[sender] = match_idx
            self.next_index[sender] = match_idx + 1

            # Check if majority agreement reached for any uncommitted entries
            for n in range(self.commit_index + 1, len(self.log)):
                if self.log[n].term == self.current_term:
                    replicated_count = 1 + sum(1 for p in self.peers if self.match_index.get(p, 0) >= n)
                    if replicated_count > self.total_nodes // 2:
                        self.commit_index = n
                        self._apply_committed_entries()
        else:
            # Step back next_index and retry
            self.next_index[sender] = max(1, self.next_index.get(sender, len(self.log)) - 1)
            p_idx = self.next_index[sender] - 1
            p_term = self.log[p_idx].term if p_idx < len(self.log) else 0
            entries = [e.to_dict() for e in self.log[p_idx + 1 :]]
            return [(
                sender,
                "AppendEntries",
                {
                    "term": self.current_term,
                    "leader_id": self.node_id,
                    "prev_log_index": p_idx,
                    "prev_log_term": p_term,
                    "entries": entries,
                    "leader_commit": self.commit_index,
                },
            )]

        return []

    def handle_client_write(
        self,
        key: str,
        value: Any,
        now_us: VirtualMicroseconds,
    ) -> list[tuple[NodeId, str, dict[str, Any]]]:
        """Handle client write request by appending to log and replicating."""
        if self.role != RaftRole.LEADER:
            # In simulation, forward to known leader or return empty
            return []

        entry = LogEntry(
            index=len(self.log),
            term=self.current_term,
            command=("put", key, value),
        )
        self.log.append(entry)
        self.match_index[self.node_id] = entry.index

        outbound: list[tuple[NodeId, str, dict[str, Any]]] = []
        for peer in self.peers:
            p_idx = self.next_index.get(peer, entry.index) - 1
            p_term = self.log[p_idx].term if p_idx < len(self.log) else 0
            entries = [e.to_dict() for e in self.log[p_idx + 1 :]]
            outbound.append((
                peer,
                "AppendEntries",
                {
                    "term": self.current_term,
                    "leader_id": self.node_id,
                    "prev_log_index": p_idx,
                    "prev_log_term": p_term,
                    "entries": entries,
                    "leader_commit": self.commit_index,
                },
            ))
        return outbound

    def _apply_committed_entries(self) -> None:
        """Apply newly committed log entries to the local key-value state machine."""
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            entry = self.log[self.last_applied]
            op, key, val = entry.command
            if op == "put":
                self.kv_store[key] = val

    def get_state_snapshot(self) -> dict[str, Any]:
        """Return the current committed key-value state."""
        return dict(self.kv_store)

    def recover(self, now_us: VirtualMicroseconds) -> None:
        """Reboot node after crash, resetting volatile role to FOLLOWER."""
        super().recover(now_us)
        self.role = RaftRole.FOLLOWER
        self.votes_received.clear()
        self.last_leader_contact_us = now_us
