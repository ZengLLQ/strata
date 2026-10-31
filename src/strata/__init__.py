"""Strata: A Python-first Distributed Systems Engineering and Fault-Injection Framework."""

__version__ = "0.1.0"
__author__ = "Strata Engineering Team"

from strata.core.experiment import ExperimentDefinition
from strata.simulation.engine import DeterministicSimulationEngine

__all__ = [
    "ExperimentDefinition",
    "DeterministicSimulationEngine",
    "__version__",
]
