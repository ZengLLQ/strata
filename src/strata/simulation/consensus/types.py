"""Data structures and types for Raft distributed consensus."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class RaftRole(str, Enum):
    """Operational consensus role of a Raft node."""

    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


@dataclass(frozen=True)
class LogEntry:
    """Replicated log entry holding term, index, and state-machine command."""

    index: int
    term: int
    command: tuple[str, str, Any]  # (op_type, key, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "term": self.term,
            "command": list(self.command),
        }
