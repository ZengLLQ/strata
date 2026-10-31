"""Benchmark execution engine, trial sampling, and performance distribution aggregation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import time
from typing import Any, Callable
from pydantic import BaseModel, ConfigDict, Field, model_validator

from strata.adapters.harness import IntegrationHarness
from strata.analysis.metrics import (
    MetricDistribution,
    calculate_distribution,
    compute_throughput_metrics,
)
from strata.core.experiment import ExperimentDefinition
from strata.core.types import ExecutionMode
from strata.simulation.engine import DeterministicSimulationEngine, RunResult


class BenchmarkConfig(BaseModel):
    """Configuration governing repeated benchmark execution trials."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    iterations: int = Field(default=5, ge=1, description="Total number of iterations to execute")
    warmup_iterations: int = Field(default=1, ge=0, description="Initial untracked iterations for cache warming")
    seed_step: int = Field(default=1, ge=0, description="Seed increment per trial for variance testing")
    output_dir: str = Field(default="./artifacts", description="Directory to persist benchmark reports")

    @model_validator(mode="after")
    def validate_warmup_less_than_iterations(self) -> BenchmarkConfig:
        if self.warmup_iterations >= self.iterations:
            raise ValueError(
                f"warmup_iterations ({self.warmup_iterations}) must be strictly less than total iterations ({self.iterations})"
            )
        return self


@dataclass(frozen=True)
class BenchmarkSample:
    """Performance metrics captured from an individual benchmark trial."""

    trial_index: int
    is_warmup: bool
    seed: int
    events_processed: int
    final_virtual_time_us: int
    wall_clock_duration_s: float
    throughput_events_per_sec: float
    throughput_ops_per_sec: float
    speedup_factor: float
    all_invariants_passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial_index": self.trial_index,
            "is_warmup": self.is_warmup,
            "seed": self.seed,
            "events_processed": self.events_processed,
            "final_virtual_time_us": self.final_virtual_time_us,
            "wall_clock_duration_s": round(self.wall_clock_duration_s, 6),
            "throughput_events_per_sec": round(self.throughput_events_per_sec, 2),
            "throughput_ops_per_sec": round(self.throughput_ops_per_sec, 2),
            "speedup_factor": round(self.speedup_factor, 2),
            "all_invariants_passed": self.all_invariants_passed,
        }


@dataclass(frozen=True)
class BenchmarkResult:
    """Aggregated statistical outcome across multiple benchmark trial samples."""

    experiment_id: str
    execution_mode: str
    total_trials: int
    warmup_trials: int
    samples: list[BenchmarkSample]
    throughput_events_per_sec: MetricDistribution
    throughput_ops_per_sec: MetricDistribution
    speedup_factor: MetricDistribution
    wall_clock_duration_s: MetricDistribution
    virtual_time_us: MetricDistribution
    events_processed: MetricDistribution

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "execution_mode": self.execution_mode,
            "total_trials": self.total_trials,
            "warmup_trials": self.warmup_trials,
            "metrics": {
                "throughput_events_per_sec": self.throughput_events_per_sec.to_dict(),
                "throughput_ops_per_sec": self.throughput_ops_per_sec.to_dict(),
                "speedup_factor": self.speedup_factor.to_dict(),
                "wall_clock_duration_s": self.wall_clock_duration_s.to_dict(),
                "virtual_time_us": self.virtual_time_us.to_dict(),
                "events_processed": self.events_processed.to_dict(),
            },
            "samples": [s.to_dict() for s in self.samples],
        }


class BenchmarkRunner:
    """Executes multi-trial benchmark sweeps against simulation or integration experiments."""

    def __init__(self, config: BenchmarkConfig | None = None) -> None:
        self.config = config or BenchmarkConfig()

    def run(
        self,
        experiment: ExperimentDefinition,
        progress_callback: Callable[[int, int, bool], None] | None = None,
    ) -> BenchmarkResult:
        """Execute all warmup and measured trials, collecting statistical distributions."""
        all_samples: list[BenchmarkSample] = []
        base_seed = experiment.execution.seed
        mode = experiment.execution.mode

        for trial in range(self.config.iterations):
            is_warmup = trial < self.config.warmup_iterations
            trial_seed = base_seed + trial * self.config.seed_step

            if progress_callback:
                progress_callback(trial + 1, self.config.iterations, is_warmup)

            # Build copy with trial seed
            trial_exp = experiment.model_copy(
                update={"execution": experiment.execution.model_copy(update={"seed": trial_seed})}
            )

            # Execute run
            if mode == ExecutionMode.INTEGRATION:
                harness = IntegrationHarness(experiment=trial_exp)
                run_res: RunResult = harness.run()
            else:
                engine = DeterministicSimulationEngine(experiment=trial_exp)
                run_res = engine.run()

            # Calculate metrics
            ops_count = trial_exp.workload.operations_count
            throughput = compute_throughput_metrics(
                events_processed=run_res.events_processed,
                operations_count=ops_count,
                wall_clock_duration_s=run_res.wall_clock_duration_s,
            )

            speedup = 0.0
            if run_res.wall_clock_duration_s > 0:
                virtual_s = run_res.final_virtual_time_us / 1_000_000.0
                speedup = virtual_s / run_res.wall_clock_duration_s

            sample = BenchmarkSample(
                trial_index=trial,
                is_warmup=is_warmup,
                seed=trial_seed,
                events_processed=run_res.events_processed,
                final_virtual_time_us=run_res.final_virtual_time_us,
                wall_clock_duration_s=run_res.wall_clock_duration_s,
                throughput_events_per_sec=throughput["events_per_second"],
                throughput_ops_per_sec=throughput["operations_per_second"],
                speedup_factor=speedup,
                all_invariants_passed=run_res.all_invariants_passed,
            )
            all_samples.append(sample)

        # Separate warmup from tracked samples
        tracked_samples = [s for s in all_samples if not s.is_warmup]

        # Calculate distributions over tracked samples
        events_tput_dist = calculate_distribution([s.throughput_events_per_sec for s in tracked_samples])
        ops_tput_dist = calculate_distribution([s.throughput_ops_per_sec for s in tracked_samples])
        speedup_dist = calculate_distribution([s.speedup_factor for s in tracked_samples])
        wall_dist = calculate_distribution([s.wall_clock_duration_s for s in tracked_samples])
        vtime_dist = calculate_distribution([float(s.final_virtual_time_us) for s in tracked_samples])
        events_count_dist = calculate_distribution([float(s.events_processed) for s in tracked_samples])

        return BenchmarkResult(
            experiment_id=experiment.metadata.id,
            execution_mode=mode.value,
            total_trials=self.config.iterations,
            warmup_trials=self.config.warmup_iterations,
            samples=tracked_samples,
            throughput_events_per_sec=events_tput_dist,
            throughput_ops_per_sec=ops_tput_dist,
            speedup_factor=speedup_dist,
            wall_clock_duration_s=wall_dist,
            virtual_time_us=vtime_dist,
            events_processed=events_count_dist,
        )
