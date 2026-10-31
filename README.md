# Strata

**Strata** is a Python-first Distributed Systems Engineering and Fault-Injection Framework. It enables distributed systems researchers, reliability engineers, and software architects to define, execute, observe, and evaluate distributed failure scenarios under deterministic discrete-event simulation.

---

## Core Principles & Guarantees

1. **Deterministic Discrete-Event Simulation**: Virtual time is decoupled from wall-clock execution. The simulation clock advances strictly from event to event, measured in integer virtual microseconds (`VirtualTime`).
2. **Total Event Ordering Contract**: Events sharing identical timestamps and priority tiers are scheduled via a deterministic 3-tuple key:
   $$\text{Key} = (\text{timestamp\_us}, \text{priority}, \text{sequence\_id})$$
   where `sequence_id` is an auto-incrementing integer assigned when an event is queued. This guarantees identical event traces across repeated seeded runs.
3. **Explicit Failure Lifecycle**: Faults are modeled as distinct phases: `SCHEDULED` $\rightarrow$ `APPLIED` $\rightarrow$ `OBSERVED`.
4. **Reproducible Evidence**: Every experiment execution streams an append-only JSONL event log (`events.jsonl`), generates cryptographic SHA-256 manifests (`manifest.json`), and persists relational run metadata in SQLite (`strata_runs.db`).

---

## Architecture Overview

```
                      ┌────────────────────────────────────────┐
                      │    Experiment Definition (YAML/JSON)   │
                      └───────────────────┬────────────────────┘
                                          │ Pydantic v2 Validation
                                          ▼
                      ┌────────────────────────────────────────┐
                      │   Deterministic Simulation Engine      │
                      │ ┌──────────────┐    ┌────────────────┐ │
                      │ │ VirtualClock │    │ Priority Queue │ │
                      │ └──────────────┘    └────────────────┘ │
                      └───────┬────────────────────────┬───────┘
                              │                        │
             Simulated Routes │                        │ Injected Failures
                              ▼                        ▼
       ┌──────────────────────────────┐        ┌──────────────────────────────┐
       │   Simulated Network Layer    │        │       Fault Injector         │
       │ (Latency, Jitter, Partitions)│        │   (Node Crash, Recovery)     │
       └──────────────┬───────────────┘        └──────────────┬───────────────┘
                      │                                       │
                      ▼                                       ▼
       ┌──────────────────────────────────────────────────────────────┐
       │                 Simulated Nodes (e.g. KV Store)              │
       │           Node-1 (Coord) ── Node-2 ── Node-3 (Replicas)      │
       └──────────────────────────────┬───────────────────────────────┘
                                      │
                     Dispatched Event Stream (JSONL)
                                      ▼
       ┌──────────────────────────────┴───────────────────────────────┐
       │                     Evidence & Invariants                    │
       │ ┌─────────────────────────┐     ┌──────────────────────────┐ │
       │ │ StateConvergenceCheck   │     │ SQLite Metadata & WAL    │ │
       │ └─────────────────────────┘     └──────────────────────────┘ │
       │ ┌─────────────────────────┐     ┌──────────────────────────┐ │
       │ │ FaultObservedCheck      │     │ SHA-256 ArtifactManifest │ │
       │ └─────────────────────────┘     └──────────────────────────┘ │
       └──────────────────────────────────────────────────────────────┘
```

---

## Installation

Strata requires Python 3.11, 3.12, or 3.13.

Using `uv`:
```bash
uv pip install -e .
```

Or using standard `pip`:
```bash
pip install -e .
```

---

## Command Line Interface (CLI)

Strata provides a Typer-powered CLI with structured terminal diagnostics.

### 1. Validate Experiment Configuration
Validate an experiment definition without running the simulation:
```bash
strata validate examples/three_node_crash.yaml
```

Output highlights topology, scheduled faults, invariants, and network configurations, strictly rejecting unknown fields or invalid node references.

### 2. Execute Simulation or Integration Run
Execute an experiment specification under either deterministic simulation or real-system integration mode:
```bash
# Run deterministic discrete-event simulation with KV nodes
strata run examples/three_node_crash.yaml

# Run 3-node Raft consensus cluster with failover and linearizability check
strata run examples/raft_cluster.yaml

# Run real-system integration experiment against an HTTP microservice cluster
strata run examples/integration_http_cluster.yaml
```

Options:
- `--seed <int>` / `-s`: Override the random seed for reproducible variance.
- `--output-dir <path>` / `-o`: Specify destination directory for artifacts and SQLite database.

> [!NOTE]
> When `mode: "integration"` is set in the experiment definition, Strata runs using `IntegrationHarness`. Real-system execution operates on physical wall-clock time and is explicitly labeled non-deterministic. All destructive actions (process killing, volume deletion) are disabled by default and require `allow_destructive: true`.

### 3. Inspect Experiment Runs & Event Timelines
Inspect execution metadata, invariant verdicts, and chronological event timelines:
```bash
strata inspect <RUN_ID>
```

Options:
- `--events` / `-e`: Display the chronological event timeline table.
- `--limit <int>` / `-n`: Maximum number of timeline events to display (default: 50).
- `--artifacts-dir <path>` / `-d`: Directory containing `strata_runs.db` (default: `./artifacts`).

### 4. Verify Experiment Artifact Bundle Integrity
Cryptographically verify manifest presence and SHA-256 checksums of core artifacts (`events.jsonl`, `experiment.yaml`, `run_summary.json`):
```bash
strata verify <RUN_ID>
```

Options:
- `--artifacts-dir <path>` / `-d`: Directory containing artifact bundles (default: `./artifacts`).

Exit codes: `0` = bundle verified and untampered; `1` = missing or corrupted artifacts.

### 5. Compare Experiment Runs (Differential Analysis)
Perform comparative differential analysis between two experiment runs (e.g. baseline vs. chaos-injected run):
```bash
strata compare <RUN_A> <RUN_B>
```

Options:
- `--artifacts-dir <path>` / `-d`: Directory containing `strata_runs.db` (default: `./artifacts`).

Computes differential metrics (virtual duration delta, event count delta, wall-clock delta), invariant verdict transitions (`UNCHANGED`, `REGRESSION`, `IMPROVED`, `ADDED`, `REMOVED`), and per-node key-value state differences.

### 6. Benchmark Performance, Throughput & Speedup
Run repeated benchmark trials with statistical distribution analysis:
```bash
strata benchmark examples/three_node_crash.yaml --iterations 5 --warmup 1
```

Options:
- `--iterations <int>` / `-n`: Total benchmark trials to execute (default: 5).
- `--warmup <int>` / `-w`: Number of warmup iterations discarded from statistics (default: 1).
- `--output-dir <path>` / `-o`: Directory to save `benchmark_summary.json` and `benchmark_report.md`.
- `--json` / `--no-json`: Toggle JSON export (default: true).
- `--markdown` / `--no-markdown`: Toggle Markdown export (default: true).

---

## Programmatic Python SDK

You can construct and execute experiments directly in Python:

```python
from pathlib import Path
from strata.core.experiment import (
    ExperimentDefinition, ExperimentMetadata, ExecutionConfig,
    TopologyConfig, NodeConfig, NetworkConfig, WorkloadConfig,
    FaultConfig, InvariantConfig, ArtifactsConfig
)
from strata.simulation.engine import DeterministicSimulationEngine

# Define experiment
experiment = ExperimentDefinition(
    metadata=ExperimentMetadata(
        id="exp_sdk_demo",
        name="SDK Demo Simulation",
    ),
    execution=ExecutionConfig(seed=1337, deterministic=True),
    topology=TopologyConfig(
        nodes=[
            NodeConfig(id="node-1", role="coordinator"),
            NodeConfig(id="node-2", role="replica"),
            NodeConfig(id="node-3", role="replica"),
        ],
        network=NetworkConfig(default_latency_us=1000),
    ),
    workload=WorkloadConfig(
        workload_type="replicated_kv",
        operations_count=5,
        arrival_interval_us=5000,
        target_nodes=["node-1"],
    ),
    faults=[
        FaultConfig(
            id="crash_node_2",
            fault_type="node_crash",
            target="node-2",
            trigger_time_us=12000,
            duration_us=15000,  # Recovers at t=27000us
        )
    ],
    invariants=[
        InvariantConfig(id="inv_fault_check", invariant_type="fault_observed"),
        InvariantConfig(id="inv_no_panic", invariant_type="no_panic"),
    ],
    artifacts=ArtifactsConfig(output_dir="./artifacts"),
)

# Run simulation
engine = DeterministicSimulationEngine(experiment=experiment)
result = engine.run()

print(f"Run ID: {result.run_id}")
print(f"Events Processed: {result.events_processed}")
print(f"All Invariants Passed: {result.all_invariants_passed}")
```

### Real-System Integration Execution

You can also run experiments directly against live HTTP services using `IntegrationHarness`:

```python
from strata.adapters.harness import IntegrationHarness
from strata.adapters.http import HttpServiceAdapter

# Define endpoints and instantiate adapter
adapter = HttpServiceAdapter(
    endpoints={"node-1": "http://127.0.0.1:8001", "node-2": "http://127.0.0.1:8002"},
    allow_destructive=False,
)

# Run integration harness against live external cluster
harness = IntegrationHarness(experiment=integ_experiment, adapter=adapter)
integ_result = harness.run()
```

---

## Implemented Subsystems vs. Roadmap

| Subsystem | Implemented in Current Release | Planned in Later Phases |
| :--- | :--- | :--- |
| **Simulation Core** | Integer microsecond VirtualClock, PriorityEventQueue total ordering, isolated RNG, runaway limit guards, dynamic packet drop & delay filters, Raft distributed consensus state machines | Byzantine fault models |
| **Fault Injection** | Node crash and recovery, bilateral network partitions and healing, message drops, message delays, simulated clock skew and frequency drift | Packet bit corruption, Byzantine faults |
| **Topology & Nodes** | Replicated key-value store, Raft consensus nodes with leader election and log replication | Custom user-defined node actor protocol |
| **Invariants** | State convergence, fault observation, panic-free execution, partition isolation, formal sequential linearizability checking (Porcupine model) | TLA+ specification parity |
| **Evidence & Storage** | Streaming JSONL event log, SQLite metadata with WAL, SHA-256 manifests, `strata inspect` timeline, `strata verify` bundle checker, `strata compare` differential analysis | Visual web console, time-travel debugger |
| **Integration Harness** | BaseServiceAdapter, HttpServiceAdapter, DockerEnvironmentManager, IntegrationHarness with real wall-clock execution, safety guardrails | Kubernetes / cloud adapters |
| **Benchmarking & Observability** | Multi-trial sweeps (`strata benchmark`), statistical distributions (mean, stddev, percentiles), speedup factor, OpenTelemetry provider | Automated regression alerting |

---

## Running Automated Tests

Run the full test suite with pytest:
```bash
pytest -v
```

Run property-based tests (Hypothesis):
```bash
pytest tests/property/ -v
```

Run determinism regression tests:
```bash
pytest tests/integration/test_determinism_regression.py -v
```
