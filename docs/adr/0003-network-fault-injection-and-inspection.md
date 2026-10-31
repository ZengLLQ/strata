# ADR 0003: Network Fault Models, Dynamic Rules, and Run Inspection

## Status
Accepted

## Context
Phase 1 established deterministic discrete-event scheduling, virtual time, and node crash/restart faults.
Distributed systems frequently experience non-fail-stop network anomalies: asymmetrical partitions, split-brain scenarios, transient packet loss bursts, and degraded link latency.
Furthermore, operators and researchers need an auditable command-line interface (`strata inspect`) to examine historical runs, view invariant verdicts, and trace the event timeline directly from persisted SQLite metadata and JSONL logs.

## Decisions

### 1. Network Partition and Healing Model
- Partitions are defined between two disjoint subsets of nodes: $\text{Group}_A$ and $\text{Group}_B$.
- When a `network_partition` fault triggers at virtual time $t_{trigger}$, bidirectional communication between any node $a \in \text{Group}_A$ and $b \in \text{Group}_B$ is cut.
- Intra-group communication ($\forall a_1, a_2 \in \text{Group}_A$) remains fully intact.
- If a duration is specified, a `network_heal` fault is scheduled at $t_{trigger} + \text{duration}$.
- Healing restores communication without mutating inflight messages already dropped.

### 2. Dynamic Message Filtering (Delay and Drop Rules)
- `SimulatedNetwork` supports dynamic fault filters registered via discrete events:
  - **Message Drop Filter**: Drops matching messages (by source, target, or message_type) during a time window $[t_{start}, t_{end}]$.
  - **Message Delay Filter**: Adds deterministic $\Delta t$ latency to matching messages during a time window.
- Filters are evaluated in deterministic order before base link latency and jitter.

### 3. Partition Isolation Invariant
- A dedicated invariant (`PartitionIsolationInvariant`) verifies that during the active partition window $[t_{start}, t_{end}]$, no message whose origin is in $\text{Group}_A$ and destination is in $\text{Group}_B$ (or vice-versa) was delivered.
- References relevant message delivery attempt events as evidence.

### 4. Run Inspection Architecture (`strata inspect`)
- `strata inspect RUN_ID` queries the relational SQLite repository (`strata_runs.db`).
- Reconstructs run execution metadata, invariant results, and fault records.
- If the artifact directory is present, inspects `manifest.json` and parses `events.jsonl` to render a formatted event timeline table with virtual timestamps, priority tiers, sources, and targets.

## Consequences
- Full support for split-brain and degraded network experiments.
- High visibility into historical runs without needing to parse raw JSONL files manually.
- Preserves 100% determinism: network faults and filter rules rely solely on virtual timestamps and the engine's isolated pseudo-random number generator.
