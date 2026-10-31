# ADR 0002: Explicit Fault Lifecycle and Replicated Key-Value Model

## Status
Accepted

## Context
In distributed systems simulation and chaos testing, failure injection is often loosely defined, conflating the configuration of a fault with its physical activation and subsequent system impact.
Furthermore, validating simulation behavior requires an initial reference distributed state machine that executes realistic protocol operations (read, write, replica propagation) without introducing complex third-party dependencies.

## Decisions

### 1. Three-Phase Fault Lifecycle
Every fault in Strata implements a three-phase transition lifecycle:
1. `SCHEDULED`: Defined in the experiment specification with a target, trigger virtual timestamp $t_{trigger}$, duration $\Delta t$, and parameters.
2. `APPLIED`: Activated by the simulation engine at virtual time $t_{trigger}$, modifying node or network state and emitting a `fault.applied` audit event.
3. `OBSERVED`: Evaluated by invariant checkers against system telemetry and recorded events to confirm the fault produced observable distributed effects.

### 2. Node Crash and Recovery Semantics
- `NodeCrashFault`: At $t_{trigger}$, transitions the target node from `ONLINE` to `OFFLINE`.
- While `OFFLINE`, a node rejects client operations and drops incoming network messages.
- If `duration_us` is configured, the engine automatically schedules a `NodeRestartFault` at $t_{trigger} + \Delta t$, transitioning the node back to `ONLINE` and triggering state recovery.

### 3. Replicated Key-Value State Machine (`ReplicatedKVNode`)
- Implements a master-replica key-value store across simulated nodes.
- Coordinator node accepts `client_write` operations, commits locally, and sends asynchronous `replicate_request` messages across the simulated network to replicas.
- Replicas update local key-value state and reply with `replicate_ack`.

## Consequences
- Clean separation between scheduled fault definitions, engine application, and invariant assertions.
- Predictable failure injection with auditable trace events.
