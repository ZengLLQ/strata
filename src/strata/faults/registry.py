"""Registry mapping fault configuration types to fault implementations."""

from __future__ import annotations

from typing import Type

from strata.core.errors import UnsupportedFaultError
from strata.core.experiment import FaultConfig
from strata.faults.base import BaseFault
from strata.faults.clock import ClockSkewFault, ClockSkewResetFault
from strata.faults.crash import NodeCrashFault, NodeRestartFault
from strata.faults.network import (
    MessageDelayFault,
    MessageDropFault,
    NetworkHealFault,
    NetworkPartitionFault,
)


class FaultRegistry:
    """Registry managing available fault types."""

    _REGISTRY: dict[str, Type[BaseFault]] = {
        "node_crash": NodeCrashFault,
        "node_restart": NodeRestartFault,
        "network_partition": NetworkPartitionFault,
        "network_heal": NetworkHealFault,
        "message_drop": MessageDropFault,
        "message_delay": MessageDelayFault,
        "clock_skew": ClockSkewFault,
        "clock_skew_reset": ClockSkewResetFault,
    }

    @classmethod
    def register(cls, fault_type: str, fault_cls: Type[BaseFault]) -> None:
        """Register a new fault type implementation."""
        cls._REGISTRY[fault_type] = fault_cls

    @classmethod
    def create_from_config(cls, config: FaultConfig) -> BaseFault:
        """Instantiate a fault from a validated FaultConfig object."""
        fault_cls = cls._REGISTRY.get(config.fault_type)
        if fault_cls is None:
            supported = sorted(cls._REGISTRY.keys())
            raise UnsupportedFaultError(
                f"Unsupported fault type '{config.fault_type}'. Supported types: {supported}"
            )

        if config.fault_type == "node_crash":
            return NodeCrashFault(
                fault_id=config.id,
                target=config.target,
                trigger_time_us=config.trigger_time_us,
                duration_us=config.duration_us,
                parameters=config.parameters,
            )
        elif config.fault_type == "node_restart":
            return NodeRestartFault(
                fault_id=config.id,
                target=config.target,
                trigger_time_us=config.trigger_time_us,
                parameters=config.parameters,
            )
        elif config.fault_type == "network_partition":
            return NetworkPartitionFault(
                fault_id=config.id,
                group_a=config.parameters.get("group_a", []),
                group_b=config.parameters.get("group_b", []),
                trigger_time_us=config.trigger_time_us,
                duration_us=config.duration_us,
                parameters=config.parameters,
            )
        elif config.fault_type == "network_heal":
            return NetworkHealFault(
                fault_id=config.id,
                group_a=config.parameters.get("group_a", []),
                group_b=config.parameters.get("group_b", []),
                trigger_time_us=config.trigger_time_us,
                parameters=config.parameters,
            )
        elif config.fault_type == "message_drop":
            return MessageDropFault(
                fault_id=config.id,
                target=config.target,
                trigger_time_us=config.trigger_time_us,
                duration_us=config.duration_us or 10_000,
                source=config.parameters.get("source"),
                message_type=config.parameters.get("message_type"),
                parameters=config.parameters,
            )
        elif config.fault_type == "message_delay":
            return MessageDelayFault(
                fault_id=config.id,
                target=config.target,
                trigger_time_us=config.trigger_time_us,
                delay_us=config.parameters.get("delay_us", 5000),
                duration_us=config.duration_us or 10_000,
                source=config.parameters.get("source"),
                message_type=config.parameters.get("message_type"),
                parameters=config.parameters,
            )
        elif config.fault_type == "clock_skew":
            params = config.parameters or {}
            raw_offset = params.get("offset_us")
            if raw_offset is None:
                raw_offset = params.get("skew_us", 0)
            offset_us = int(raw_offset) if raw_offset is not None else 0

            raw_drift = params.get("drift_ppm")
            if raw_drift is None:
                raw_rate = params.get("drift_rate")
                if raw_rate is not None:
                    raw_drift = float(raw_rate) * 1_000_000.0
                else:
                    raw_drift = 0.0
            drift_ppm = float(raw_drift)

            return ClockSkewFault(
                fault_id=config.id,
                target=config.target,
                trigger_time_us=config.trigger_time_us,
                offset_us=offset_us,
                drift_ppm=drift_ppm,
                duration_us=config.duration_us,
                parameters=config.parameters,
            )
        elif config.fault_type == "clock_skew_reset":
            return ClockSkewResetFault(
                fault_id=config.id,
                target=config.target,
                trigger_time_us=config.trigger_time_us,
                parameters=config.parameters,
            )
        else:
            return fault_cls(
                fault_id=config.id,
                target=config.target,
                trigger_time_us=config.trigger_time_us,
                duration_us=config.duration_us,
                parameters=config.parameters,
            )
