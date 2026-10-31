# ADR 0005: External Service Integration Harness, HTTP Adapters, and Docker Orchestration

## Status
Accepted

## Context
Phases 1 through 3 established Strata's deterministic discrete-event simulation kernel, supporting integer-microsecond virtual time, total event ordering, node crash/recovery models, network partitions, dynamic drop/delay filters, clock drift, cryptographic artifact manifests, and differential run comparison.

However, distributed systems engineering ultimately targets software running on physical machines, container runtimes, and real network interfaces. To validate distributed algorithms against real systems, engineers need:
1. **External Service Adapters**: Interfaces to connect Strata's workload generators and fault injection mechanisms to running processes and HTTP microservices.
2. **Local Container Orchestration**: Controlled multi-node test environments using Docker and Docker Compose without requiring cloud accounts, Kubernetes, or complex remote infrastructure.
3. **Explicit Determinism Boundaries**: Strict architectural separation between deterministic simulation and real-world execution, ensuring the framework never misleads users into believing real distributed networks are fully repeatable.
4. **Safety Guardrails**: Strict refusal of destructive actions (e.g. process killing, volume purging) unless explicitly authorized by the engineer.

## Decisions

### 1. Unified Service Adapter Contract (`ServiceAdapterContract` & `BaseServiceAdapter`)
- Defined `ServiceAdapterContract` protocol in `strata.core.contracts`.
- Implemented `BaseServiceAdapter` in `strata.adapters.base`.
- Established standard lifecycle operations:
  - `setup(timeout_seconds)`: Pre-flight environment initialization and endpoint reachability check.
  - `health_check(timeout_seconds)`: Verification of cluster readiness.
  - `execute_workload(workload_config, start_time_ns)`: Dispatches real operations, measuring physical round-trip latencies.
  - `inject_fault(fault_config, now_ns)`: Applies real-world faults via management endpoints or container lifecycle.
  - `collect_results()`: Extracts final cluster state snapshots for invariant evaluation.
  - `get_environment_metadata()`: Gathers host platform, OS, kernel, Python version, and network identifiers.
  - `get_determinism_limitations()`: Returns documented limitations regarding OS scheduling, network jitter, and black-box observability.
  - `teardown()`: Cleans up external resources and clears injected fault state.

### 2. HTTP Service Adapter (`HttpServiceAdapter`)
- Implemented in `strata.adapters.http` using Python's standard library `urllib.request` to avoid mandatory third-party network dependencies.
- Maps abstract node identifiers to HTTP base URLs (e.g. `{"node-1": "http://127.0.0.1:8001"}`).
- Translates `replicated_kv` workloads into RESTful `PUT /kv/<key>` and `GET /kv/<key>` requests, recording microsecond latency and HTTP status codes in `WorkloadOperationEvent`.
- Orchestrates faults via standard REST admin hooks:
  - `POST /admin/fault/crash` and `POST /admin/fault/restart`.
  - `POST /admin/fault/delay` (simulating network latency or thread pauses).
  - `POST /admin/fault/partition` and `POST /admin/fault/heal` (controlling peer isolation).
  - `POST /admin/reset` (restoring clean state during teardown).

### 3. Local Docker Orchestration (`DockerEnvironmentManager`)
- Implemented in `strata.adapters.docker`.
- Manages local container cluster lifecycle via Docker CLI and Docker Compose (`up -d`, `down`, `pause`, `unpause`, `restart`, `network disconnect/connect`).
- Designed for 100% offline local testing without cloud accounts or third-party orchestrators.
- Supports dependency injection of command runners for isolated unit testing without requiring a live Docker daemon.

### 4. Integration Harness (`IntegrationHarness`)
- Orchestrates experiment runs when `execution.mode == ExecutionMode.INTEGRATION`.
- Enforces strict validation: `deterministic` must be `false`.
- Uses real wall-clock microsecond timestamps: `(time.time_ns() - start_time_ns) // 1000`.
- Interleaves real-time workload dispatching with scheduled fault triggers and automated duration-based recovery.
- Exposes `IntegrationNodeProxy` so existing invariant evaluators (`StateConvergenceInvariant`, `FaultObservedInvariant`, `NoPanicInvariant`) can evaluate real-system history and cluster state identically to simulation runs.
- Produces complete `RunResult` records with `execution_mode: ExecutionMode.INTEGRATION`, cryptographic manifests, and SQLite storage.

### 5. Destructive Chaos Guardrails
- In accordance with the project's non-negotiable engineering rules, destructive actions are disabled by default.
- `allow_destructive: bool = False` is enforced across `ExecutionConfig`, `BaseServiceAdapter`, and `DockerEnvironmentManager`.
- Attempting to kill processes or delete volumes without setting `allow_destructive: true` raises `DestructiveActionRefusalError`.

## Consequences
- Enables testing both simulated algorithms and real microservice implementations using identical experiment definitions and invariant evaluators.
- Eliminates ambiguity regarding determinism by explicitly labeling integration runs as non-deterministic in all CLI outputs, reports, and metadata.
- Protects developer environments from unintended destructive actions during chaos testing.
