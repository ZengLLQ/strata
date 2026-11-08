# ADR 0002: Experiment Schema, Lifecycle Contracts, and Evidence Format

## Status
Accepted

## Context
Strata experiments must be declared in human-readable, version-controlled files (YAML or JSON) while preventing security vulnerabilities such as arbitrary code execution.
Furthermore, experiment executions must produce immutable, verifiable evidence suitable for scientific reproducibility, regression comparison, and post-mortem debugging.

## Decisions

### 1. Pydantic v2 Schema & Safe Parsing
- Experiment configurations are modeled with strict Pydantic v2 classes with `extra = "forbid"` to reject unknown or misspelt attributes.
- Parsed via `yaml.safe_load`. Custom Python tags (`!!python/object`, etc.) are explicitly rejected.
- Semantic validation verifies:
  - Unique node identifiers across the topology.
  - Workload targets and fault targets reference declared nodes.
  - Probability parameters strictly within $[0.0, 1.0]$.
  - Temporal consistency: fault recovery times occur strictly after fault trigger times.

### 2. Explicit Fault Lifecycle: Scheduled vs Applied vs Observed
Faults are modeled as distinct phases:
1. `SCHEDULED`: Declared in configuration with target node, parameters, and virtual trigger timestamp $t_{trigger}$.
2. `APPLIED`: Engine activates the fault at virtual time $t_{trigger}$, executing the failure mechanism (e.g. state transition from `ONLINE` to `OFFLINE`) and generating a `FaultAppliedEvent`.
3. `OBSERVED`: System and invariant checks measure the side effects (e.g., dropped messages, state divergence). If a node was already crashed when a crash fault triggers, the applied record notes this distinction.

### 3. Dual Storage Architecture: SQLite + JSONL
Experiment persistence is split into two complementary layers:
- **Streaming JSONL Event Log (`events.jsonl`)**:
  - Append-only event stream recording every dispatched event, message payload, fault trigger, and state change.
  - Streams incrementally to disk; survives simulation crashes or early termination.
  - Each line is a self-contained, valid JSON document containing `sequence_id`, `virtual_time_us`, `wall_clock_iso`, `event_type`, `source`, `target`, and `payload`.
- **SQLite Run Metadata Database (`strata_runs.db`)**:
  - Relational storage for high-level experiment runs, environment metadata, execution duration, invariant verdicts, and summary metrics.
  - Uses standard SQLite with WAL mode for fast concurrency and portability.

### 4. Manifest & Cryptographic Integrity
At run completion, Strata generates `manifest.json`:
- Contains run metadata, engine version, random seed, and completion status.
- Computes SHA-256 checksums for:
  - The experiment definition file.
  - `events.jsonl`.
- The manifest allows verification of artifact tampering or incomplete runs without requiring the original SQLite database.

### 5. Repository & Specification Conflicts
- **Conflict**: The master prompt mentions future research features (e.g. Paxos/Raft consensus algorithms, web consoles, Docker integration).
- **Resolution**: Phase 1 implements a lightweight replicated key-value reference model to prove end-to-end discrete-event simulation, crash injection, and state convergence. Advanced consensus, Docker adapters, and frontend dashboards are tracked as `PLANNED` for subsequent phases to maintain strict focus on correctness and clean module boundaries.

## Consequences
- Clean separation between configuration, event streaming, and relational summaries.
- Zero external database daemon needed for simulation runs.
- Experiments can be shared, archived, and inspected as self-contained directory bundles.
