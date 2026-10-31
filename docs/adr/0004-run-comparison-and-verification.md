# ADR 0004: Run Verification, Differential Experiment Comparison, and Clock Skew Faults

## Status
Accepted

## Context
Phase 1 established the deterministic discrete-event simulation kernel, node crash models, and cryptographic artifact manifests.
Phase 2 introduced network fault models (partitions, drop/delay filters) and the `strata inspect` timeline command.

To support rigorous reliability engineering and regression detection, distributed systems engineers require:
1. **Standalone Artifact Verification (`strata verify`)**: An independent command-line check verifying that an artifact bundle is complete, untampered, and cryptographically identical to its recorded manifest.
2. **Differential Run Comparison (`strata compare`)**: Comparative analysis between two completed experiment runs (e.g., baseline vs. chaos-injected run) to observe changes in virtual duration, event volume, invariant verdicts, and final replicated state.
3. **Clock Skew Simulation (`ClockSkewFault`)**: A fault mechanism to model clock drift or step offsets across distributed nodes to study time-dependent consensus and lease protocols.

## Decisions

### 1. Standalone Manifest Verification (`strata verify`)
- `strata verify RUN_ID` performs offline cryptographic validation of an experiment run artifact bundle.
- Checks the presence and syntax of `manifest.json`.
- Enforces mandatory existence and checksum matching for core evidence artifacts: `events.jsonl`, `experiment.yaml`, and `run_summary.json`.
- Yields exit code 0 when all digests match; exit code 1 upon any missing file or digest mismatch.

### 2. Differential Run Comparison Architecture (`strata compare`)
- Implemented `RunComparator` in `strata.evidence.comparison`.
- Queries `strata_runs.db` for both baseline (`RUN_A`) and target (`RUN_B`) records.
- Computes three differential dimensions:
  - **Metrics Delta**: Execution status, random seed, virtual duration delta ($\Delta t_{us}$), events processed delta ($\Delta N$), and wall-clock time delta.
  - **Invariant Verdicts**: Maps invariant IDs across both runs and categorizes transitions into `UNCHANGED`, `REGRESSION` (passed $\rightarrow$ failed/violated), `IMPROVED` (failed $\rightarrow$ passed), `ADDED` (present only in Run B), `REMOVED` (present only in Run A), or `DIVERGENT`.
  - **Node State Diff**: Performs key-level comparison across all replica stores, identifying `MODIFIED`, `ONLY_IN_A`, and `ONLY_IN_B` values.
- Renders compact, color-coded Rich tables.

### 3. Final Node State Snapshots in Run Evidence
- `DeterministicSimulationEngine` captures final key-value state snapshots from all simulated nodes upon simulation termination.
- Included in `RunResult.node_states`, serialized to `run_summary.json`, and stored in `RunRecord.summary_json`.
- `RunComparator` seamlessly falls back to bundle files or invariant details for backwards-compatible state extraction.

### 4. Simulated Clock Skew and Drift Fault (`ClockSkewFault`)
- Nodes support both constant offset (`clock_offset_us`) and linear frequency drift (`clock_drift_ppm`).
- `get_perceived_time(now_us)` calculates:
  $$\text{perceived} = \max\left(0, \text{now\_us} + \text{offset\_us} + \left\lfloor (\text{now\_us} - t_{start}) \times \frac{\text{drift\_ppm}}{10^6} \right\rfloor\right)$$
- `ClockSkewFault` injects an offset and/or drift rate into a target node at virtual timestamp $t_{trigger}$.
- If `duration_us` is specified, a `ClockSkewResetFault` is scheduled at $t_{trigger} + \text{duration}$ to restore the node's clock offset and drift back to zero.
- Registered in `FaultRegistry` under `"clock_skew"` and validated in `ExperimentDefinition` schema.

## Consequences
- Enables automated regression testing in CI pipelines by comparing candidate runs against blessed baselines.
- Provides cryptographic tamper detection without requiring full database access.
- Expands fault injection coverage to asynchronous temporal anomalies while retaining 100% determinism.
