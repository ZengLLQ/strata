# ADR 0007: Distributed Raft Consensus State Machines and Formal Linearizability Verification

## Status
Accepted

## Context
Early phases of Strata provided simple master-replica key-value replication. However, modern distributed systems research and portfolio-grade engineering require:
1. **Real Distributed Consensus**: Multi-node consensus with leader election, terms, heartbeats, and log replication based on the Raft protocol (Ongaro & Ousterhout, 2014).
2. **Formal Linearizability Verification**: Per the master engineering specification:
    > *"Do not label a system linearizable merely because all nodes eventually contain the same value. If a linearizability checker is implemented, define the history format and validate histories against an explicit sequential specification."*

## Decisions

### 1. Formal Sequential Specification Models (`SequentialModel`)
- Implemented in `strata.invariants.linearizability`.
- Defines immutable state transition semantics:
  $$\text{step}(\text{state}, \text{input}) \rightarrow (\text{valid}, \text{next\_state}, \text{output})$$
- Implemented models:
  - `SequentialRegister`: Single-register sequential read/write contract.
  - `SequentialKV`: Multi-key sequential dictionary contract supporting `put` and `get`.

### 2. Bounded State-Space Linearizability Search (`LinearizabilityChecker`)
- Explores all valid topological interleavings of concurrent client operations bounded by real-time invocation ($t_{inv}$) and return ($t_{ret}$) intervals.
- **Precedence Constraint**: If an operation $A$ returned strictly before operation $B$ was invoked ($t_{ret}^A < t_{inv}^B$), $A$ must precede $B$ in any valid linearization.
- **Key-Partitioned Optimization**: Because operations on disjoint keys in a key-value store commute, `LinearizabilityChecker` partitions the history by key, verifying each partition independently to avoid combinatorial explosion.
- **Memoization**: Explores states using bitmask visited sets `(state, completed_operations_mask)` to prune duplicate search paths.
- Generates a certified sequential linearization order upon success, or identifies specific violating operations upon failure.

### 3. Linearizability Invariant (`LinearizableKVInvariant`)
- Registered in `strata.invariants.registry` under `"linearizability"`.
- Extracts client `workload.operation` records, derives invocation and response time bounds, and evaluates the history against `SequentialKV`.
- Distinguishes:
  - `PASSED`: Certified linearization order exists.
  - `VIOLATED`: Operation history cannot be linearized against the sequential specification.
  - `INCONCLUSIVE`: Zero operations executed or search bounds exceeded.

### 4. Raft Consensus Node State Machine (`RaftNode`)
- Implemented in `strata.simulation.consensus.raft.RaftNode`.
- State Machine:
  - Roles: `FOLLOWER`, `CANDIDATE`, `LEADER`.
  - Persistent state: `current_term`, `voted_for`, `log` (with sentinel entry at index 0).
  - Volatile state: `commit_index`, `last_applied`, `next_index`, `match_index`.
- RPCs:
  - `RequestVote` and `RequestVoteResponse`: Election timeout triggers term increment, candidate transition, and majority vote tallying.
  - `AppendEntries` and `AppendEntriesResponse`: Leader broadcasts heartbeats; followers replicate entries and commit.
- Virtual Discrete-Event Timers:
  - Election timeouts and heartbeat intervals are scheduled as discrete events (`node.timer_tick`) in Strata's `PriorityEventQueue`, preserving 100% deterministic simulation reproducibility.
- Client Requests:
  - Client writes submitted to the cluster are handled by the Leader, appended to the log, replicated to peers, committed upon majority agreement, and applied to the local `kv_store`.

## Consequences
- Guarantees true safety and correctness evaluation for distributed protocols under chaos without relying on hand-wavy eventual consistency heuristics.
- Fulfills the master specification mandate for formal history validation against sequential specifications.
- Positions Strata as a credible distributed systems research and portfolio platform.
