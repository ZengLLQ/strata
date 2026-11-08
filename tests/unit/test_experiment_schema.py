"""Unit tests for ExperimentDefinition schema validation and strict error rejection."""

import pytest
from strata.core.errors import ConfigurationError
from strata.core.experiment import ExperimentDefinition


def test_valid_yaml_parsing() -> None:
    yaml_content = """
schema_version: "1.0.0"
metadata:
  id: "exp_valid"
  name: "Valid Experiment"
topology:
  nodes:
    - id: "n1"
      role: "coordinator"
    - id: "n2"
      role: "replica"
workload:
  workload_type: "replicated_kv"
  operations_count: 5
  arrival_interval_us: 1000
faults:
  - id: "f1"
    fault_type: "node_crash"
    target: "n2"
    trigger_time_us: 5000
"""
    exp = ExperimentDefinition.from_yaml(yaml_content)
    assert exp.metadata.id == "exp_valid"
    assert len(exp.topology.nodes) == 2
    assert len(exp.faults) == 1
    assert exp.faults[0].target == "n2"


def test_rejects_extra_unsupported_fields() -> None:
    yaml_content = """
schema_version: "1.0.0"
metadata:
  id: "exp_extra"
  name: "Extra Field Experiment"
  unsupported_attribute: "malicious_or_accidental"
topology:
  nodes:
    - id: "n1"
"""
    with pytest.raises(ConfigurationError, match="Extra inputs are not permitted"):
        ExperimentDefinition.from_yaml(yaml_content)


def test_rejects_duplicate_node_ids() -> None:
    yaml_content = """
schema_version: "1.0.0"
metadata:
  id: "exp_dup_nodes"
  name: "Duplicate Nodes"
topology:
  nodes:
    - id: "node-dup"
    - id: "node-dup"
"""
    with pytest.raises(ConfigurationError, match="Duplicate node IDs declared"):
        ExperimentDefinition.from_yaml(yaml_content)


def test_rejects_fault_targeting_unknown_node() -> None:
    yaml_content = """
schema_version: "1.0.0"
metadata:
  id: "exp_bad_target"
  name: "Bad Fault Target"
topology:
  nodes:
    - id: "node-1"
faults:
  - id: "f1"
    fault_type: "node_crash"
    target: "non-existent-node"
    trigger_time_us: 1000
"""
    with pytest.raises(ConfigurationError, match="targets unknown node"):
        ExperimentDefinition.from_yaml(yaml_content)


def test_rejects_invalid_drop_rate_probability() -> None:
    yaml_content = """
schema_version: "1.0.0"
metadata:
  id: "exp_bad_rate"
  name: "Bad Drop Rate"
topology:
  nodes:
    - id: "node-1"
  network:
    default_drop_rate: 1.5
"""
    with pytest.raises(ConfigurationError, match="less than or equal to 1.0"):
        ExperimentDefinition.from_yaml(yaml_content)


def test_rejects_non_mapping_yaml() -> None:
    with pytest.raises(ConfigurationError, match="must be a YAML mapping"):
        ExperimentDefinition.from_yaml("- a list instead of a dict")
