"""Versioned, validated experiment schema definitions using Pydantic v2."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from strata.core.errors import ConfigurationError, TopologyError
from strata.core.types import ExecutionMode, NodeState


class StrictBaseModel(BaseModel):
    """Base model enforcing strict validation and forbidding undeclared fields."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        frozen=True,
    )


class ExperimentMetadata(StrictBaseModel):
    """Identity and informational metadata for an experiment."""

    id: str = Field(..., min_length=1, pattern=r"^[a-zA-Z0-9_\-\.]+$", description="Unique experiment ID")
    name: str = Field(..., min_length=1, description="Human-readable title")
    version: str = Field(default="1.0.0", description="Schema/experiment version")
    description: str = Field(default="", description="Detailed experiment hypothesis or context")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")


class ExecutionConfig(StrictBaseModel):
    """Execution parameters including seed and mode."""

    mode: ExecutionMode = Field(default=ExecutionMode.SIMULATION, description="Execution mode")
    seed: int = Field(default=42, ge=0, description="Random seed for deterministic runs")
    deterministic: bool = Field(default=True, description="Enforce strict determinism guarantees")
    allow_destructive: bool = Field(
        default=False,
        description="Explicit authorization for destructive real-system actions in integration mode",
    )


class NodeConfig(StrictBaseModel):
    """Configuration for an individual distributed node in the topology."""

    id: str = Field(..., min_length=1, pattern=r"^[a-zA-Z0-9_\-\.]+$", description="Node identifier")
    role: str = Field(default="replica", description="Role of the node (e.g. coordinator, replica)")
    initial_state: NodeState = Field(default=NodeState.ONLINE, description="Starting lifecycle state")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Node-specific configuration parameters")


class NetworkLinkConfig(StrictBaseModel):
    """Network connection characteristics between two nodes."""

    source: str = Field(..., min_length=1)
    target: str = Field(..., min_length=1)
    latency_us: int = Field(default=1000, ge=0, description="One-way latency in microseconds")
    jitter_us: int = Field(default=0, ge=0, description="Maximum jitter in microseconds")
    drop_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Probability of dropped packets")


class NetworkConfig(StrictBaseModel):
    """Global and per-link simulated network configuration."""

    default_latency_us: int = Field(default=1000, ge=0, description="Default latency in microseconds")
    default_jitter_us: int = Field(default=0, ge=0, description="Default latency jitter in microseconds")
    default_drop_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Default message loss rate")
    links: list[NetworkLinkConfig] = Field(default_factory=list, description="Explicit link overrides")


class TopologyConfig(StrictBaseModel):
    """Topological configuration of nodes and communication links."""

    nodes: list[NodeConfig] = Field(..., min_length=1, description="Declared nodes in cluster")
    network: NetworkConfig = Field(default_factory=NetworkConfig, description="Network simulation parameters")

    @field_validator("nodes")
    @classmethod
    def validate_unique_node_ids(cls, nodes: list[NodeConfig]) -> list[NodeConfig]:
        seen: set[str] = set()
        duplicates: list[str] = []
        for node in nodes:
            if node.id in seen:
                duplicates.append(node.id)
            seen.add(node.id)
        if duplicates:
            raise ValueError(f"Duplicate node IDs declared in topology: {duplicates}")
        return nodes


class FaultConfig(StrictBaseModel):
    """Configuration for an individual scheduled fault."""

    id: str = Field(..., min_length=1, pattern=r"^[a-zA-Z0-9_\-\.]+$", description="Unique fault ID")
    fault_type: str = Field(..., min_length=1, description="Fault type (e.g. node_crash, node_restart)")
    target: str = Field(..., min_length=1, description="Target node or link identifier")
    trigger_time_us: int = Field(..., ge=0, description="Virtual activation timestamp in microseconds")
    duration_us: int | None = Field(default=None, ge=0, description="Fault duration before automatic recovery")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Fault-specific parameters")


class WorkloadConfig(StrictBaseModel):
    """Configuration for the workload generator."""

    workload_type: str = Field(default="replicated_kv", description="Workload generator identifier")
    operations_count: int = Field(default=10, gt=0, description="Total operations to execute")
    arrival_interval_us: int = Field(default=5000, ge=0, description="Interval between operations in microseconds")
    key_space_size: int = Field(default=5, gt=0, description="Number of distinct keys in workload")
    target_nodes: list[str] = Field(default_factory=list, description="Specific nodes to target with workload")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Custom workload parameters")


class InvariantConfig(StrictBaseModel):
    """Specification of an invariant to evaluate against the run history."""

    id: str = Field(..., min_length=1, description="Stable identifier for the invariant")
    invariant_type: str = Field(..., min_length=1, description="Registered invariant evaluator name")
    description: str = Field(default="", description="Explanation of what this invariant asserts")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Evaluation parameters")


class ResourceLimitsConfig(StrictBaseModel):
    """Guard rails preventing runaway or unbounded execution."""

    max_virtual_time_us: int = Field(default=10_000_000, gt=0, description="Max virtual time (default 10s)")
    max_events: int = Field(default=100_000, gt=0, description="Max event loop iterations")
    wall_clock_timeout_seconds: float = Field(default=30.0, gt=0.0, description="Real wall-clock timeout")


class ArtifactsConfig(StrictBaseModel):
    """Storage and output artifact locations."""

    output_dir: str = Field(default="./artifacts", description="Directory for logs and SQLite database")
    persist_sqlite: bool = Field(default=True, description="Write run summary to SQLite")
    persist_jsonl: bool = Field(default=True, description="Stream all events to JSONL")


class ExperimentDefinition(StrictBaseModel):
    """Root validated specification of a Strata experiment."""

    schema_version: str = Field(default="1.0.0", description="Strata schema version")
    metadata: ExperimentMetadata
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    topology: TopologyConfig
    workload: WorkloadConfig = Field(default_factory=WorkloadConfig)
    faults: list[FaultConfig] = Field(default_factory=list)
    invariants: list[InvariantConfig] = Field(default_factory=list)
    limits: ResourceLimitsConfig = Field(default_factory=ResourceLimitsConfig)
    artifacts: ArtifactsConfig = Field(default_factory=ArtifactsConfig)

    @model_validator(mode="after")
    def validate_cross_field_references(self) -> ExperimentDefinition:
        """Verify that all node references across faults and workloads exist in topology."""
        if self.execution.mode == ExecutionMode.INTEGRATION and self.execution.deterministic:
            raise ValueError(
                "Real-system integration mode cannot provide deterministic guarantees. "
                "Set 'deterministic: false' in execution configuration."
            )

        valid_node_ids = {node.id for node in self.topology.nodes}

        # Check fault targets
        for fault in self.faults:
            if fault.fault_type in ("node_crash", "node_restart") and fault.target not in valid_node_ids:
                raise ValueError(
                    f"Fault '{fault.id}' targets unknown node '{fault.target}'. "
                    f"Declared nodes: {sorted(valid_node_ids)}"
                )
            elif fault.fault_type in ("network_partition", "network_heal"):
                group_a = fault.parameters.get("group_a", [])
                group_b = fault.parameters.get("group_b", [])
                if not isinstance(group_a, list) or not isinstance(group_b, list):
                    raise ValueError(
                        f"Fault '{fault.id}' requires 'group_a' and 'group_b' lists in parameters."
                    )
                if not group_a or not group_b:
                    raise ValueError(
                        f"Fault '{fault.id}' cannot have empty partition groups."
                    )
                for node_id in group_a:
                    if node_id not in valid_node_ids:
                        raise ValueError(f"Partition fault '{fault.id}' references unknown node in group_a: '{node_id}'")
                for node_id in group_b:
                    if node_id not in valid_node_ids:
                        raise ValueError(f"Partition fault '{fault.id}' references unknown node in group_b: '{node_id}'")
                intersection = set(group_a) & set(group_b)
                if intersection:
                    raise ValueError(
                        f"Partition groups in fault '{fault.id}' must be disjoint, found overlap: {intersection}"
                    )
            elif fault.fault_type == "message_delay":
                delay_us = fault.parameters.get("delay_us", 0)
                if not isinstance(delay_us, int) or delay_us <= 0:
                    raise ValueError(f"Fault '{fault.id}' requires positive integer 'delay_us' in parameters.")
            elif fault.fault_type in ("clock_skew", "clock_skew_reset"):
                if fault.target not in valid_node_ids:
                    raise ValueError(
                        f"Fault '{fault.id}' targets unknown node '{fault.target}'. "
                        f"Declared nodes: {sorted(valid_node_ids)}"
                    )
                if fault.fault_type == "clock_skew":
                    offset = fault.parameters.get("offset_us", fault.parameters.get("skew_us"))
                    drift_ppm = fault.parameters.get("drift_ppm")
                    drift_rate = fault.parameters.get("drift_rate")

                    if offset is None and drift_ppm is None and drift_rate is None:
                        raise ValueError(
                            f"Clock skew fault '{fault.id}' requires integer 'offset_us' (or 'skew_us') "
                            f"or numeric 'drift_ppm' / 'drift_rate' in parameters."
                        )
                    if offset is not None:
                        if isinstance(offset, bool) or not isinstance(offset, int):
                            raise ValueError(
                                f"Clock skew fault '{fault.id}' requires integer 'offset_us' (or 'skew_us') in parameters."
                            )
                    if drift_ppm is not None:
                        if isinstance(drift_ppm, bool) or not isinstance(drift_ppm, (int, float)):
                            raise ValueError(
                                f"Clock skew fault '{fault.id}' requires numeric 'drift_ppm' in parameters."
                            )
                    if drift_rate is not None:
                        if isinstance(drift_rate, bool) or not isinstance(drift_rate, (int, float)):
                            raise ValueError(
                                f"Clock skew fault '{fault.id}' requires numeric 'drift_rate' in parameters."
                            )

        # Check workload target nodes
        for target in self.workload.target_nodes:
            if target not in valid_node_ids:
                raise ValueError(
                    f"Workload targets unknown node '{target}'. "
                    f"Declared nodes: {sorted(valid_node_ids)}"
                )

        # Check network links
        for link in self.topology.network.links:
            if link.source not in valid_node_ids:
                raise ValueError(f"Link source '{link.source}' is not a declared node.")
            if link.target not in valid_node_ids:
                raise ValueError(f"Link target '{link.target}' is not a declared node.")

        return self

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ExperimentDefinition:
        """Create and validate an ExperimentDefinition from a dictionary."""
        try:
            return cls.model_validate(data)
        except Exception as exc:
            raise ConfigurationError(f"Experiment validation failed: {exc}") from exc

    @classmethod
    def from_yaml(cls, source: str | Path) -> ExperimentDefinition:
        """Load and strictly validate an experiment from a YAML file or string."""
        raw_text: str
        if isinstance(source, Path) or (isinstance(source, str) and (source.endswith(".yaml") or source.endswith(".yml")) and Path(source).is_file()):
            path = Path(source)
            if not path.exists():
                raise ConfigurationError(f"Experiment file not found: {path}")
            raw_text = path.read_text(encoding="utf-8")
        else:
            raw_text = str(source)

        try:
            # safe_load strictly prevents arbitrary Python code execution
            parsed = yaml.safe_load(raw_text)
        except yaml.YAMLError as err:
            raise ConfigurationError(f"Malformed YAML in experiment specification: {err}") from err

        if not isinstance(parsed, dict):
            raise ConfigurationError("Experiment specification must be a YAML mapping (dictionary).")

        return cls.from_dict(parsed)
