"""Clock skew fault implementations for simulated node time drift."""

from __future__ import annotations

from typing import Any, Mapping

from strata.core.errors import FaultApplicationError
from strata.core.types import VirtualMicroseconds
from strata.faults.base import BaseFault
from strata.simulation.events import FaultAppliedEvent


class ClockSkewFault(BaseFault):
    """Fault that injects simulated clock skew/offset and frequency drift into a target node."""

    def __init__(
        self,
        fault_id: str,
        target: str,
        trigger_time_us: VirtualMicroseconds,
        offset_us: int = 0,
        drift_ppm: float = 0.0,
        duration_us: VirtualMicroseconds | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            fault_id=fault_id,
            fault_type="clock_skew",
            target=target,
            trigger_time_us=trigger_time_us,
            duration_us=duration_us,
            parameters=parameters,
        )
        params = dict(parameters or {})
        if offset_us != 0:
            self.offset_us = offset_us
        else:
            raw_offset = params.get("offset_us")
            if raw_offset is None:
                raw_offset = params.get("skew_us", 0)
            self.offset_us = int(raw_offset) if raw_offset is not None else 0

        if drift_ppm != 0.0:
            self.drift_ppm = float(drift_ppm)
        else:
            raw_drift = params.get("drift_ppm")
            if raw_drift is None:
                raw_rate = params.get("drift_rate")
                if raw_rate is not None:
                    raw_drift = float(raw_rate) * 1_000_000.0
                else:
                    raw_drift = 0.0
            self.drift_ppm = float(raw_drift)

    def apply(self, engine: Any, now_us: VirtualMicroseconds) -> dict[str, Any]:
        """Apply clock skew and drift to target node."""
        node = engine.nodes.get(self.target)
        if node is None:
            raise FaultApplicationError(f"Cannot apply clock skew to unknown node '{self.target}'")

        previous_offset = getattr(node, "clock_offset_us", 0)
        previous_drift = getattr(node, "clock_drift_ppm", 0.0)
        if hasattr(node, "set_clock_skew"):
            node.set_clock_skew(offset_us=self.offset_us, drift_ppm=self.drift_ppm, now_us=now_us)
        else:
            node.set_clock_offset(self.offset_us)

        reset_time_us: VirtualMicroseconds | None = None
        if self.duration_us is not None and self.duration_us > 0:
            reset_time_us = now_us + self.duration_us
            reset_fault = ClockSkewResetFault(
                fault_id=f"{self.fault_id}_reset",
                target=self.target,
                trigger_time_us=reset_time_us,
            )
            engine.schedule_fault(reset_fault)

        evidence = {
            "node_id": self.target,
            "previous_offset_us": previous_offset,
            "previous_drift_ppm": previous_drift,
            "new_offset_us": self.offset_us,
            "new_drift_ppm": self.drift_ppm,
            "perceived_time_us": node.get_perceived_time(now_us),
            "reset_scheduled_at_us": reset_time_us,
        }
        self.mark_applied(now_us, evidence)

        fault_event = FaultAppliedEvent.create(
            sequence_id=engine.next_sequence_id(),
            timestamp_us=now_us,
            fault_id=self.fault_id,
            fault_type=self.fault_type,
            target=self.target,
            evidence=evidence,
        )
        engine.record_event(fault_event)
        return evidence


class ClockSkewResetFault(BaseFault):
    """Fault that resets clock offset and drift for a target node back to zero."""

    def __init__(
        self,
        fault_id: str,
        target: str,
        trigger_time_us: VirtualMicroseconds,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            fault_id=fault_id,
            fault_type="clock_skew_reset",
            target=target,
            trigger_time_us=trigger_time_us,
            duration_us=None,
            parameters=parameters,
        )

    def apply(self, engine: Any, now_us: VirtualMicroseconds) -> dict[str, Any]:
        """Reset target node's clock offset and drift back to zero."""
        node = engine.nodes.get(self.target)
        if node is None:
            raise FaultApplicationError(f"Cannot reset clock skew on unknown node '{self.target}'")

        previous_offset = getattr(node, "clock_offset_us", 0)
        previous_drift = getattr(node, "clock_drift_ppm", 0.0)
        node.reset_clock_offset()

        evidence = {
            "node_id": self.target,
            "previous_offset_us": previous_offset,
            "previous_drift_ppm": previous_drift,
            "new_offset_us": 0,
            "new_drift_ppm": 0.0,
            "perceived_time_us": node.get_perceived_time(now_us),
        }
        self.mark_applied(now_us, evidence)

        fault_event = FaultAppliedEvent.create(
            sequence_id=engine.next_sequence_id(),
            timestamp_us=now_us,
            fault_id=self.fault_id,
            fault_type=self.fault_type,
            target=self.target,
            evidence=evidence,
        )
        engine.record_event(fault_event)
        return evidence
