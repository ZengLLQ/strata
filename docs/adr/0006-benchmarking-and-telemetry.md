# ADR 0006: Performance Benchmarking, Statistical Metrics Analysis, and Observability Telemetry

## Status
Accepted

## Context
Phases 1 through 4 established the deterministic simulation core, fault injection models, evidence persistence, and real-system integration adapters.

To evaluate distributed system reliability and simulation efficiency, engineers need:
1. **Performance Benchmarking (`strata benchmark`)**: The ability to run multi-trial benchmark sweeps to measure event throughput, operational latency, and simulation speedup without manual orchestration.
2. **Statistical Analysis**: Formal distribution metrics (mean, standard deviation, min, max, median, p90, p95, p99 percentiles) to assess performance stability and variance across trials.
3. **Observability Integration**: OpenTelemetry tracing and metrics instrumentation to observe experiment runs, fault injections, and workload execution while maintaining zero mandatory external dependencies.

## Decisions

### 1. Statistical Distribution Model (`MetricDistribution` & `calculate_distribution`)
- Implemented in `strata.analysis.metrics`.
- Calculates comprehensive statistical metrics: `count`, `min`, `max`, `mean`, `median` (p50), `stddev`, `p90`, `p95`, `p99`.
- Implements percentile calculations using linear rank interpolation:
  $$\text{rank} = \frac{p}{100} \times (n - 1)$$
- Built using the Python standard library with zero external dependencies (no numpy or scipy required).

### 2. Multi-Trial Benchmark Engine (`BenchmarkRunner` & `BenchmarkResult`)
- Implemented in `strata.analysis.benchmark`.
- Configurable via `BenchmarkConfig`:
  - `iterations`: Total number of trials to run.
  - `warmup_iterations`: Initial untracked runs to prime internal caches and JIT paths.
  - `seed_step`: Seed increment across trials to test seed-induced variance.
- Supports both `ExecutionMode.SIMULATION` and `ExecutionMode.INTEGRATION`.
- Measures:
  - Event throughput: $\text{throughput}_{\text{events}} = \frac{N_{\text{events}}}{\Delta t_{\text{wall}}}$
  - Operation throughput: $\text{throughput}_{\text{ops}} = \frac{N_{\text{ops}}}{\Delta t_{\text{wall}}}$
  - Speedup factor: $S = \frac{\Delta t_{\text{virtual}}}{\Delta t_{\text{wall}}}$
- Generates aggregated `BenchmarkResult` capturing statistical distributions over all measured trials.

### 3. OpenTelemetry Provider Pattern (`StrataTelemetry`)
- Implemented in `strata.analysis.telemetry`.
- Provides unified tracing context managers (`trace_span`) and metric recorders (`record_counter`, `record_histogram`).
- Employs a zero-overhead `NoOpSpan` pattern:
  - If `opentelemetry` is installed and `enabled=True`, forwards to real OpenTelemetry Tracer and Meter instances.
  - If disabled or uninstalled, operates as a null object with zero overhead and no runtime errors.
- Includes in-memory collector mode for testing and local inspection without requiring a live OpenTelemetry Collector daemon.

### 4. Benchmark CLI Command (`strata benchmark PATH`)
- Implemented in `strata.cli.benchmark_cmd` and registered in `strata.cli.main`.
- Interactive execution with Rich progress indicators.
- Renders:
  - Summary Panel (mean throughput, ops rate, speedup factor, wall duration).
  - Statistical Distributions Table (mean, stddev, min, median, p90, p95, max).
- Automatically exports `benchmark_summary.json` and `benchmark_report.md` to the specified artifacts directory.

## Consequences
- Completes all CLI commands specified in the master prompt (`validate`, `run`, `inspect`, `verify`, `compare`, `benchmark`).
- Provides reproducible performance data for research papers, engineering portfolios, and CI regression tracking.
- Maintains zero mandatory external runtime dependencies for core simulation and analysis.
