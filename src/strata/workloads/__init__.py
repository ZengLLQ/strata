"""Workload generation subsystem for Strata."""

from strata.workloads.base import BaseWorkload
from strata.workloads.kv import ReplicatedKVWorkload

__all__ = [
    "BaseWorkload",
    "ReplicatedKVWorkload",
]
