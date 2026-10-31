"""Network fault implementations: partitions, healing, message drops, and delays."""

from __future__ import annotations

from typing import Any, Mapping

from strata.core.errors import FaultApplicationError
from strata.core.types import FaultPhase, VirtualMicroseconds
from strata.faults.base import BaseFault
from strata.simulation.events import FaultAppliedEvent
from strata.simulation.network import MessageDelayRule, MessageDropRule


class NetworkPartitionFault(BaseFault):
    """Partitions network communication between two groups of nodes."""

    def __init__(
        self,
        fault_id: str,
        group_a: list[str],
        group_b: list[str],
        trigger_time_us: VirtualMicroseconds,
        duration_us: VirtualMicroseconds | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            fault_id=fault_id,
            fault_type="network_partition",
            target=f"partition:{','.join(sorted(group_a))}||{','.join(sorted(group_b))}",
            trigger_time_us=trigger_time_us,
            duration_us=duration_us,
            parameters=parameters,
        )
        self.group_a = set(group_a)
        self.group_b = set(group_b)

    def apply(self, engine: Any, now_us: VirtualMicroseconds) -> dict[str, Any]:
        """Apply bidirectional network partition on the simulated network."""
        engine.network.add_partition(self.group_a, self.group_b)

        heal_time_us: VirtualMicroseconds | None = None
        if self.duration_us is not None and self.duration_us > 0:
            heal_time_us = now_us + self.duration_us
            heal_fault = NetworkHealFault(
                fault_id=f"{self.fault_id}_heal",
                group_a=list(self.group_a),
                group_b=list(self.group_b),
                trigger_time_us=heal_time_us,
            )
            engine.schedule_fault(heal_fault)

        evidence = {
            "group_a": sorted(self.group_a),
            "group_b": sorted(self.group_b),
            "heal_scheduled_at_us": heal_time_us,
        }
        self.mark_applied(now_us, evidence)

        event = FaultAppliedEvent.create(
            sequence_id=engine.next_sequence_id(),
            timestamp_us=now_us,
            fault_id=self.fault_id,
            fault_type=self.fault_type,
            target=self.target,
            evidence=evidence,
        )
        engine.record_event(event)
        return evidence


class NetworkHealFault(BaseFault):
    """Heals an active network partition between node groups."""

    def __init__(
        self,
        fault_id: str,
        group_a: list[str],
        group_b: list[str],
        trigger_time_us: VirtualMicroseconds,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            fault_id=fault_id,
            fault_type="network_heal",
            target=f"heal:{','.join(sorted(group_a))}||{','.join(sorted(group_b))}",
            trigger_time_us=trigger_time_us,
            duration_us=None,
            parameters=parameters,
        )
        self.group_a = set(group_a)
        self.group_b = set(group_b)

    def apply(self, engine: Any, now_us: VirtualMicroseconds) -> dict[str, Any]:
        """Heal network partition."""
        engine.network.remove_partition(self.group_a, self.group_b)

        evidence = {
            "healed_group_a": sorted(self.group_a),
            "healed_group_b": sorted(self.group_b),
        }
        self.mark_applied(now_us, evidence)

        event = FaultAppliedEvent.create(
            sequence_id=engine.next_sequence_id(),
            timestamp_us=now_us,
            fault_id=self.fault_id,
            fault_type=self.fault_type,
            target=self.target,
            evidence=evidence,
        )
        engine.record_event(event)
        return evidence


class MessageDropFault(BaseFault):
    """Injects a time-windowed rule dropping matching messages."""

    def __init__(
        self,
        fault_id: str,
        target: str,
        trigger_time_us: VirtualMicroseconds,
        duration_us: VirtualMicroseconds = 10_000,
        source: str | None = None,
        message_type: str | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            fault_id=fault_id,
            fault_type="message_drop",
            target=target,
            trigger_time_us=trigger_time_us,
            duration_us=duration_us,
            parameters=parameters,
        )
        self.source = source
        self.message_type = message_type

    def apply(self, engine: Any, now_us: VirtualMicroseconds) -> dict[str, Any]:
        end_time_us = now_us + (self.duration_us or 0)
        rule = MessageDropRule(
            rule_id=self.fault_id,
            source=self.source,
            target=self.target,
            message_type=self.message_type,
            start_time_us=now_us,
            end_time_us=end_time_us,
        )
        engine.network.add_drop_rule(rule)

        evidence = {
            "source": self.source,
            "target": self.target,
            "message_type": self.message_type,
            "start_time_us": now_us,
            "end_time_us": end_time_us,
        }
        self.mark_applied(now_us, evidence)

        event = FaultAppliedEvent.create(
            sequence_id=engine.next_sequence_id(),
            timestamp_us=now_us,
            fault_id=self.fault_id,
            fault_type=self.fault_type,
            target=self.target,
            evidence=evidence,
        )
        engine.record_event(event)
        return evidence


class MessageDelayFault(BaseFault):
    """Injects a time-windowed rule adding latency to matching messages."""

    def __init__(
        self,
        fault_id: str,
        target: str,
        trigger_time_us: VirtualMicroseconds,
        delay_us: VirtualMicroseconds,
        duration_us: VirtualMicroseconds = 10_000,
        source: str | None = None,
        message_type: str | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(
            fault_id=fault_id,
            fault_type="message_delay",
            target=target,
            trigger_time_us=trigger_time_us,
            duration_us=duration_us,
            parameters=parameters,
        )
        self.delay_us = delay_us
        self.source = source
        self.message_type = message_type

    def apply(self, engine: Any, now_us: VirtualMicroseconds) -> dict[str, Any]:
        end_time_us = now_us + (self.duration_us or 0)
        rule = MessageDelayRule(
            rule_id=self.fault_id,
            source=self.source,
            target=self.target,
            message_type=self.message_type,
            delay_us=self.delay_us,
            start_time_us=now_us,
            end_time_us=end_time_us,
        )
        engine.network.add_delay_rule(rule)

        evidence = {
            "source": self.source,
            "target": self.target,
            "delay_us": self.delay_us,
            "start_time_us": now_us,
            "end_time_us": end_time_us,
        }
        self.mark_applied(now_us, evidence)

        event = FaultAppliedEvent.create(
            sequence_id=engine.next_sequence_id(),
            timestamp_us=now_us,
            fault_id=self.fault_id,
            fault_type=self.fault_type,
            target=self.target,
            evidence=evidence,
        )
        engine.record_event(event)
        return evidence
