"""Fault injection subsystem for Strata."""

from strata.faults.base import BaseFault
from strata.faults.clock import ClockSkewFault, ClockSkewResetFault
from strata.faults.crash import NodeCrashFault, NodeRestartFault
from strata.faults.network import (
    MessageDelayFault,
    MessageDropFault,
    NetworkHealFault,
    NetworkPartitionFault,
)
from strata.faults.registry import FaultRegistry

__all__ = [
    "BaseFault",
    "NodeCrashFault",
    "NodeRestartFault",
    "NetworkPartitionFault",
    "NetworkHealFault",
    "MessageDropFault",
    "MessageDelayFault",
    "ClockSkewFault",
    "ClockSkewResetFault",
    "FaultRegistry",
]
