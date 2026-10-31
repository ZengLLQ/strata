"""Simulated network with deterministic latency, jitter, loss, and partitions."""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any, Mapping

from strata.core.errors import UnroutableMessageError
from strata.core.experiment import NetworkConfig
from strata.core.types import NodeId, VirtualMicroseconds


@dataclass(frozen=True, slots=True)
class MessageDropRule:
    """Dynamic rule dropping messages matching criteria during a virtual time window."""

    rule_id: str
    source: str | None
    target: str | None
    message_type: str | None
    start_time_us: VirtualMicroseconds
    end_time_us: VirtualMicroseconds

    def matches(
        self,
        source: NodeId,
        target: NodeId,
        message_type: str,
        now_us: VirtualMicroseconds,
    ) -> bool:
        if not (self.start_time_us <= now_us <= self.end_time_us):
            return False
        if self.source and self.source != "*" and self.source != source:
            return False
        if self.target and self.target != "*" and self.target != target:
            return False
        if self.message_type and self.message_type != "*" and self.message_type != message_type:
            return False
        return True


@dataclass(frozen=True, slots=True)
class MessageDelayRule:
    """Dynamic rule injecting latency into messages matching criteria during a virtual time window."""

    rule_id: str
    source: str | None
    target: str | None
    message_type: str | None
    delay_us: VirtualMicroseconds
    start_time_us: VirtualMicroseconds
    end_time_us: VirtualMicroseconds

    def matches(
        self,
        source: NodeId,
        target: NodeId,
        message_type: str,
        now_us: VirtualMicroseconds,
    ) -> bool:
        if not (self.start_time_us <= now_us <= self.end_time_us):
            return False
        if self.source and self.source != "*" and self.source != source:
            return False
        if self.target and self.target != "*" and self.target != target:
            return False
        if self.message_type and self.message_type != "*" and self.message_type != message_type:
            return False
        return True


class SimulatedNetwork:
    """Simulated network layer providing controlled latency, loss, partitions, and dynamic filters.
    
    All randomness is explicitly passed via a seeded random.Random instance.
    """

    def __init__(
        self,
        config: NetworkConfig,
        valid_nodes: set[NodeId],
        rng: random.Random,
    ) -> None:
        self.config = config
        self.valid_nodes = set(valid_nodes)
        self.rng = rng

        # Explicit per-link configuration (source, target) -> link_config
        self._link_configs: dict[tuple[NodeId, NodeId], Any] = {
            (link.source, link.target): link for link in config.links
        }

        # Active partitions: set of frozenset({node_a, node_b}) that cannot communicate
        self._partitions: set[frozenset[NodeId]] = set()

        # Dynamic fault rules
        self._drop_rules: dict[str, MessageDropRule] = {}
        self._delay_rules: dict[str, MessageDelayRule] = {}

        # Telemetry metrics
        self.messages_sent: int = 0
        self.messages_delivered: int = 0
        self.messages_dropped: int = 0
        self.messages_partitioned: int = 0

    def add_partition(self, group_a: set[NodeId], group_b: set[NodeId]) -> None:
        """Create a bidirectional network partition between two sets of nodes."""
        for a in group_a:
            for b in group_b:
                self._partitions.add(frozenset([a, b]))

    def remove_partition(self, group_a: set[NodeId], group_b: set[NodeId]) -> None:
        """Heal a network partition between two sets of nodes."""
        for a in group_a:
            for b in group_b:
                self._partitions.discard(frozenset([a, b]))

    def heal_all_partitions(self) -> None:
        """Remove all network partitions."""
        self._partitions.clear()

    def is_partitioned(self, source: NodeId, target: NodeId) -> bool:
        """Check if communication between source and target is partitioned."""
        return frozenset([source, target]) in self._partitions

    def add_drop_rule(self, rule: MessageDropRule) -> None:
        """Register a dynamic message drop rule."""
        self._drop_rules[rule.rule_id] = rule

    def remove_drop_rule(self, rule_id: str) -> None:
        """Remove a dynamic message drop rule."""
        self._drop_rules.pop(rule_id, None)

    def add_delay_rule(self, rule: MessageDelayRule) -> None:
        """Register a dynamic message delay rule."""
        self._delay_rules[rule.rule_id] = rule

    def remove_delay_rule(self, rule_id: str) -> None:
        """Remove a dynamic message delay rule."""
        self._delay_rules.pop(rule_id, None)

    def calculate_delivery(
        self,
        source: NodeId,
        target: NodeId,
        current_time_us: VirtualMicroseconds,
        message_type: str = "default",
    ) -> tuple[bool, VirtualMicroseconds, str]:
        """Calculate whether a message will be delivered, its arrival time, and drop reason.
        
        Returns:
            (will_deliver: bool, arrival_time_us: VirtualMicroseconds, status_reason: str)
        """
        self.messages_sent += 1

        if source not in self.valid_nodes:
            raise UnroutableMessageError(f"Source node '{source}' is not in network topology.")
        if target not in self.valid_nodes:
            raise UnroutableMessageError(f"Target node '{target}' is not in network topology.")

        # 1. Check network partition
        if self.is_partitioned(source, target):
            self.messages_partitioned += 1
            return False, current_time_us, "network_partition"

        # 2. Check dynamic drop rules
        for drop_rule in self._drop_rules.values():
            if drop_rule.matches(source, target, message_type, current_time_us):
                self.messages_dropped += 1
                return False, current_time_us, f"fault_drop:{drop_rule.rule_id}"

        # 3. Determine base link parameters
        link = self._link_configs.get((source, target))
        latency = link.latency_us if link else self.config.default_latency_us
        jitter = link.jitter_us if link else self.config.default_jitter_us
        drop_rate = link.drop_rate if link else self.config.default_drop_rate

        # 4. Check dynamic delay rules
        extra_delay_us = 0
        for delay_rule in self._delay_rules.values():
            if delay_rule.matches(source, target, message_type, current_time_us):
                extra_delay_us += delay_rule.delay_us

        # 5. Stochastic drop check
        if drop_rate > 0.0 and self.rng.random() < drop_rate:
            self.messages_dropped += 1
            return False, current_time_us, "packet_loss"

        # 6. Stochastic jitter calculation
        actual_jitter = self.rng.randint(-jitter, jitter) if jitter > 0 else 0
        total_latency = max(0, latency + actual_jitter + extra_delay_us)
        arrival_time_us = current_time_us + total_latency

        self.messages_delivered += 1
        return True, arrival_time_us, "delivered"
