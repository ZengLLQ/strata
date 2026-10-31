"""Unit tests for the Raft consensus state machine node."""

from __future__ import annotations

import pytest

from strata.core.types import NodeState
from strata.simulation.consensus.raft import (
    LogEntry,
    RaftNode,
    RaftRole,
)


def test_raft_node_initialization() -> None:
    """Raft node initializes as Follower with term 0 and empty log."""
    node = RaftNode(node_id="node-1", peers=["node-2", "node-3"])
    assert node.role == RaftRole.FOLLOWER
    assert node.current_term == 0
    assert node.voted_for is None
    assert len(node.log) == 1  # Index 0 is dummy root entry
    assert node.commit_index == 0


def test_raft_election_timeout_becomes_candidate() -> None:
    """Election timeout transitions Follower to Candidate and broadcasts RequestVote."""
    node = RaftNode(node_id="node-1", peers=["node-2", "node-3"], election_timeout_us=100000)
    
    # Trigger election timeout at t=150000us
    outbound = node.check_timers(now_us=150000)

    assert node.role == RaftRole.CANDIDATE
    assert node.current_term == 1
    assert node.voted_for == "node-1"
    assert len(outbound) == 2  # RequestVote sent to node-2 and node-3

    target_nodes = [target for target, msg_type, _ in outbound]
    assert "node-2" in target_nodes
    assert "node-3" in target_nodes
    for _, msg_type, payload in outbound:
        assert msg_type == "RequestVote"
        assert payload["term"] == 1
        assert payload["candidate_id"] == "node-1"


def test_raft_candidate_receives_majority_votes_becomes_leader() -> None:
    """Candidate receiving majority votes transitions to Leader and broadcasts heartbeats."""
    node = RaftNode(node_id="node-1", peers=["node-2", "node-3"], election_timeout_us=100000)
    node.check_timers(now_us=150000)  # Becomes Candidate, term 1, 1 vote (self)

    # Receive vote from node-2 (1 + 1 = 2 out of 3 -> majority!)
    resp = {
        "term": 1,
        "vote_granted": True,
        "voter_id": "node-2",
    }
    outbound = node.on_message(sender="node-2", message_type="RequestVoteResponse", payload=resp, now_us=160000)

    assert node.role == RaftRole.LEADER
    # Leader immediately broadcasts heartbeats (AppendEntries) to peers
    assert len(outbound) == 2
    for _, msg_type, payload in outbound:
        assert msg_type == "AppendEntries"
        assert payload["term"] == 1
        assert payload["entries"] == []


def test_raft_follower_grants_vote_to_candidate() -> None:
    """Follower grants vote if candidate has higher term and up-to-date log."""
    node = RaftNode(node_id="node-2", peers=["node-1", "node-3"])
    
    req = {
        "term": 1,
        "candidate_id": "node-1",
        "last_log_index": 0,
        "last_log_term": 0,
    }
    outbound = node.on_message(sender="node-1", message_type="RequestVote", payload=req, now_us=10000)

    assert len(outbound) == 1
    target, msg_type, payload = outbound[0]
    assert target == "node-1"
    assert msg_type == "RequestVoteResponse"
    assert payload["vote_granted"] is True
    assert node.voted_for == "node-1"
    assert node.current_term == 1


def test_raft_leader_replicates_log_and_commits() -> None:
    """Leader appends client command, replicates to majority, and advances commit_index."""
    leader = RaftNode(node_id="node-1", peers=["node-2", "node-3"])
    leader.role = RaftRole.LEADER
    leader.current_term = 1

    # Client write
    outbound = leader.handle_client_write(key="alpha", value="val_100", now_us=1000)
    assert len(leader.log) == 2
    assert leader.log[1].command == ("put", "alpha", "val_100")
    assert len(outbound) == 2  # Replicated to node-2 and node-3

    # node-2 responds with success
    resp_2 = {
        "term": 1,
        "success": True,
        "match_index": 1,
        "follower_id": "node-2",
    }
    leader.on_message(sender="node-2", message_type="AppendEntriesResponse", payload=resp_2, now_us=2000)

    # Majority reached (node-1 + node-2 = 2/3)! Commit index should advance to 1
    assert leader.commit_index == 1
    # State machine applies committed entry
    assert leader.kv_store.get("alpha") == "val_100"


def test_raft_step_down_on_higher_term() -> None:
    """Any node discovering higher term steps down to Follower."""
    node = RaftNode(node_id="node-1", peers=["node-2", "node-3"])
    node.role = RaftRole.LEADER
    node.current_term = 1

    # Higher term heartbeat arrives
    heartbeat = {
        "term": 5,
        "leader_id": "node-2",
        "prev_log_index": 0,
        "prev_log_term": 0,
        "entries": [],
        "leader_commit": 0,
    }
    node.on_message(sender="node-2", message_type="AppendEntries", payload=heartbeat, now_us=5000)

    assert node.role == RaftRole.FOLLOWER
    assert node.current_term == 5
