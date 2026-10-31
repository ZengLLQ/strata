"""Streaming JSONL event log writer and reader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from strata.core.types import EventPriority
from strata.simulation.events import BaseEvent


class JsonlEventLogger:
    """Incremental, append-only JSONL event logger."""

    def __init__(self, log_path: Path | str) -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.log_path, "a", encoding="utf-8")

    def log(self, event: BaseEvent) -> None:
        """Stream an event immediately to the JSONL log file with flush."""
        data = event.to_dict()
        line = json.dumps(data, ensure_ascii=False) + "\n"
        self._file.write(line)
        self._file.flush()

    def close(self) -> None:
        """Close the underlying file descriptor."""
        if not self._file.closed:
            self._file.flush()
            self._file.close()

    def __enter__(self) -> JsonlEventLogger:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    @classmethod
    def read_events(cls, path: Path | str) -> list[BaseEvent]:
        """Read and parse all events from a JSONL file."""
        events: list[BaseEvent] = []
        path = Path(path)
        if not path.exists():
            return events

        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                d = json.loads(stripped)
                event = BaseEvent(
                    sequence_id=d["sequence_id"],
                    timestamp_us=d["timestamp_us"],
                    priority=EventPriority(d["priority"]),
                    event_type=d["event_type"],
                    source=d.get("source"),
                    target=d.get("target"),
                    payload=d.get("payload", {}),
                    wall_clock_iso=d.get("wall_clock_iso", ""),
                )
                events.append(event)
        return events
