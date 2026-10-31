"""Replicated key-value workload generator."""

from __future__ import annotations

from typing import Any

from strata.core.experiment import WorkloadConfig
from strata.core.types import EventPriority
from strata.simulation.events import WorkloadOperationEvent
from strata.workloads.base import BaseWorkload


class ReplicatedKVWorkload(BaseWorkload):
    """Generates sequential key-value write operations across virtual time."""

    def __init__(self, config: WorkloadConfig) -> None:
        super().__init__(config.parameters)
        self.config = config

    def generate_events(self, engine: Any) -> None:
        """Schedule workload operation events on the engine."""
        nodes = self.config.target_nodes or [node.node_id for node in engine.experiment.topology.nodes if node.role == "coordinator"]
        if not nodes:
            nodes = [node.node_id for node in engine.experiment.topology.nodes]

        for i in range(self.config.operations_count):
            timestamp_us = (i + 1) * self.config.arrival_interval_us
            target_node = nodes[i % len(nodes)]
            key = f"key_{i % self.config.key_space_size}"
            value = f"val_{i}_{timestamp_us}"

            event = WorkloadOperationEvent.create(
                sequence_id=engine.next_sequence_id(),
                timestamp_us=timestamp_us,
                target_node=target_node,
                operation_id=f"op_{i}",
                op_type="client_write",
                key=key,
                value=value,
                priority=EventPriority.WORKLOAD_INGESTION,
            )
            engine.schedule_event(event)
