"""Differential analysis and comparison between completed experiment runs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from strata.storage.models import RunRecord


@dataclass(frozen=True)
class MetricsDelta:
    """High-level metrics comparison between two runs."""

    run_a_id: str
    run_b_id: str
    experiment_id_a: str
    experiment_id_b: str
    status_a: str
    status_b: str
    status_match: bool
    seed_a: int
    seed_b: int
    seed_match: bool
    virtual_time_a_us: int
    virtual_time_b_us: int
    virtual_time_delta_us: int
    events_a: int
    events_b: int
    events_delta: int
    wall_clock_a_s: float
    wall_clock_b_s: float
    wall_clock_delta_s: float
    all_invariants_passed_a: bool
    all_invariants_passed_b: bool
    invariants_verdict_match: bool


@dataclass(frozen=True)
class InvariantDiff:
    """Comparison of an individual invariant evaluated across two runs."""

    invariant_id: str
    invariant_type: str
    verdict_a: str | None
    verdict_b: str | None
    is_match: bool
    delta_status: str  # UNCHANGED, REGRESSION, IMPROVED, DIVERGENT
    explanation_a: str | None = None
    explanation_b: str | None = None


@dataclass(frozen=True)
class NodeKeyDiff:
    """Key-value difference on a specific node."""

    node_id: str
    key: str
    val_a: Any
    val_b: Any
    diff_type: str  # MATCH, MODIFIED, ONLY_IN_A, ONLY_IN_B


@dataclass(frozen=True)
class NodeStateDiff:
    """Per-node state comparison between two runs."""

    node_id: str
    is_identical: bool
    differences: list[NodeKeyDiff]


@dataclass(frozen=True)
class RunComparison:
    """Comprehensive differential comparison result between two experiment runs."""

    metrics: MetricsDelta
    invariants: list[InvariantDiff]
    node_diffs: dict[str, NodeStateDiff]

    @property
    def has_invariant_divergence(self) -> bool:
        """True if any invariant verdict differs between the runs."""
        return any(not inv.is_match for inv in self.invariants)

    @property
    def has_node_state_divergence(self) -> bool:
        """True if any node's final key-value state differs between the runs."""
        return any(not nd.is_identical for nd in self.node_diffs.values())

    @property
    def has_regressions(self) -> bool:
        """True if any invariant transitioned from passed to failed/violated."""
        return any(inv.delta_status == "REGRESSION" for inv in self.invariants)

    def to_dict(self) -> dict[str, Any]:
        """Serialize comparison to a structured dictionary."""
        return {
            "metrics": asdict(self.metrics),
            "invariants": [asdict(inv) for inv in self.invariants],
            "node_diffs": {
                node_id: {
                    "node_id": nd.node_id,
                    "is_identical": nd.is_identical,
                    "differences": [asdict(d) for d in nd.differences],
                }
                for node_id, nd in self.node_diffs.items()
            },
            "has_invariant_divergence": self.has_invariant_divergence,
            "has_node_state_divergence": self.has_node_state_divergence,
            "has_regressions": self.has_regressions,
        }


class RunComparator:
    """Computes differential analysis between two stored experiment runs."""

    @classmethod
    def compare_records(
        cls,
        record_a: RunRecord,
        record_b: RunRecord,
        artifacts_dir: Path | None = None,
    ) -> RunComparison:
        """Perform full differential comparison between record_a and record_b."""
        metrics = cls.diff_metrics(record_a, record_b)
        invariants = cls.diff_invariants(record_a, record_b)

        states_a = cls.extract_node_states(record_a, artifacts_dir)
        states_b = cls.extract_node_states(record_b, artifacts_dir)
        node_diffs = cls.diff_node_states(states_a, states_b)

        return RunComparison(
            metrics=metrics,
            invariants=invariants,
            node_diffs=node_diffs,
        )

    @classmethod
    def diff_metrics(cls, record_a: RunRecord, record_b: RunRecord) -> MetricsDelta:
        """Compute deltas across high-level execution metrics."""
        inv_passed_a = bool(record_a.all_invariants_passed in (1, True))
        inv_passed_b = bool(record_b.all_invariants_passed in (1, True))

        wall_a = float(record_a.wall_clock_duration_s or 0.0)
        wall_b = float(record_b.wall_clock_duration_s or 0.0)

        return MetricsDelta(
            run_a_id=record_a.run_id,
            run_b_id=record_b.run_id,
            experiment_id_a=record_a.experiment_id,
            experiment_id_b=record_b.experiment_id,
            status_a=record_a.status,
            status_b=record_b.status,
            status_match=(record_a.status == record_b.status),
            seed_a=record_a.seed,
            seed_b=record_b.seed,
            seed_match=(record_a.seed == record_b.seed),
            virtual_time_a_us=record_a.final_virtual_time_us,
            virtual_time_b_us=record_b.final_virtual_time_us,
            virtual_time_delta_us=record_b.final_virtual_time_us - record_a.final_virtual_time_us,
            events_a=record_a.events_processed,
            events_b=record_b.events_processed,
            events_delta=record_b.events_processed - record_a.events_processed,
            wall_clock_a_s=round(wall_a, 6),
            wall_clock_b_s=round(wall_b, 6),
            wall_clock_delta_s=round(wall_b - wall_a, 6),
            all_invariants_passed_a=inv_passed_a,
            all_invariants_passed_b=inv_passed_b,
            invariants_verdict_match=(inv_passed_a == inv_passed_b),
        )

    @classmethod
    def diff_invariants(cls, record_a: RunRecord, record_b: RunRecord) -> list[InvariantDiff]:
        """Compute differential verdicts across all invariants in both runs."""
        inv_a = {inv.invariant_id: inv for inv in (record_a.invariant_records or [])}
        inv_b = {inv.invariant_id: inv for inv in (record_b.invariant_records or [])}
        all_ids = sorted(set(inv_a.keys()) | set(inv_b.keys()))

        diffs: list[InvariantDiff] = []
        for inv_id in all_ids:
            a = inv_a.get(inv_id)
            b = inv_b.get(inv_id)

            verdict_a = a.verdict.lower() if a else None
            verdict_b = b.verdict.lower() if b else None
            inv_type = (a.invariant_type if a else None) or (b.invariant_type if b else "unknown")
            is_match = (verdict_a == verdict_b)

            if verdict_a is None:
                delta_status = "ADDED"
            elif verdict_b is None:
                delta_status = "REMOVED"
            elif is_match:
                delta_status = "UNCHANGED"
            elif verdict_a == "passed" and verdict_b != "passed":
                delta_status = "REGRESSION"
            elif verdict_a != "passed" and verdict_b == "passed":
                delta_status = "IMPROVED"
            else:
                delta_status = "DIVERGENT"

            diffs.append(
                InvariantDiff(
                    invariant_id=inv_id,
                    invariant_type=inv_type,
                    verdict_a=verdict_a,
                    verdict_b=verdict_b,
                    is_match=is_match,
                    delta_status=delta_status,
                    explanation_a=a.explanation if a else None,
                    explanation_b=b.explanation if b else None,
                )
            )

        return diffs

    @classmethod
    def extract_node_states(
        cls,
        record: RunRecord,
        artifacts_dir: Path | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Extract final key-value node states from record summary, artifacts, or invariant details."""
        # 1. Inspect summary_json
        if record.summary_json:
            try:
                summary_data = json.loads(record.summary_json)
                if isinstance(summary_data, dict) and "node_states" in summary_data:
                    node_states = summary_data["node_states"]
                    if isinstance(node_states, dict):
                        return node_states
            except Exception:
                pass

        # 2. Inspect run_summary.json artifact file if directory provided
        if artifacts_dir is not None:
            summary_file = Path(artifacts_dir) / record.run_id / "run_summary.json"
            if summary_file.exists():
                try:
                    data = json.loads(summary_file.read_text(encoding="utf-8"))
                    if isinstance(data, dict) and "node_states" in data and isinstance(data["node_states"], dict):
                        return data["node_states"]
                except Exception:
                    pass

        # 3. Fallback: reconstruct from StateConvergenceInvariant details if present
        if record.invariant_records:
            for inv in record.invariant_records:
                if inv.invariant_type == "state_convergence" and inv.details_json:
                    try:
                        details = json.loads(inv.details_json)
                        if "shared_state" in details and "converged_node_ids" in details:
                            shared = details["shared_state"]
                            nodes = details["converged_node_ids"]
                            return {n: dict(shared) for n in nodes}
                        elif "baseline_state" in details:
                            baseline = details["baseline_state"]
                            baseline_node = details.get("baseline_node", "node-1")
                            result = {baseline_node: dict(baseline)}
                            # If there were divergent nodes
                            for div_node, div_info in details.get("divergences", {}).items():
                                result[div_node] = {k: "DIVERGENT" for k in div_info.get("divergent_keys", [])}
                            return result
                    except Exception:
                        pass

        return {}

    @classmethod
    def diff_node_states(
        cls,
        states_a: dict[str, dict[str, Any]],
        states_b: dict[str, dict[str, Any]],
    ) -> dict[str, NodeStateDiff]:
        """Compute differences in key-value store state per node between two runs."""
        all_node_ids = sorted(set(states_a.keys()) | set(states_b.keys()))
        node_diffs: dict[str, NodeStateDiff] = {}

        for node_id in all_node_ids:
            node_map_a = states_a.get(node_id) or {}
            node_map_b = states_b.get(node_id) or {}
            if not isinstance(node_map_a, dict):
                node_map_a = {}
            if not isinstance(node_map_b, dict):
                node_map_b = {}

            all_keys = sorted(set(node_map_a.keys()) | set(node_map_b.keys()))
            differences: list[NodeKeyDiff] = []

            for key in all_keys:
                in_a = key in node_map_a
                in_b = key in node_map_b

                if in_a and not in_b:
                    differences.append(
                        NodeKeyDiff(
                            node_id=node_id,
                            key=key,
                            val_a=node_map_a[key],
                            val_b=None,
                            diff_type="ONLY_IN_A",
                        )
                    )
                elif not in_a and in_b:
                    differences.append(
                        NodeKeyDiff(
                            node_id=node_id,
                            key=key,
                            val_a=None,
                            val_b=node_map_b[key],
                            diff_type="ONLY_IN_B",
                        )
                    )
                elif node_map_a[key] != node_map_b[key]:
                    differences.append(
                        NodeKeyDiff(
                            node_id=node_id,
                            key=key,
                            val_a=node_map_a[key],
                            val_b=node_map_b[key],
                            diff_type="MODIFIED",
                        )
                    )

            if node_id in states_a and node_id not in states_b and not node_map_a:
                differences.append(
                    NodeKeyDiff(
                        node_id=node_id,
                        key="<node>",
                        val_a="<exists>",
                        val_b=None,
                        diff_type="ONLY_IN_A",
                    )
                )
            elif node_id not in states_a and node_id in states_b and not node_map_b:
                differences.append(
                    NodeKeyDiff(
                        node_id=node_id,
                        key="<node>",
                        val_a=None,
                        val_b="<exists>",
                        diff_type="ONLY_IN_B",
                    )
                )

            is_identical = len(differences) == 0
            node_diffs[node_id] = NodeStateDiff(
                node_id=node_id,
                is_identical=is_identical,
                differences=differences,
            )

        return node_diffs
