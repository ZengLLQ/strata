"""Exportable experiment evidence bundle generator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from strata.evidence.event_log import JsonlEventLogger
from strata.evidence.manifest import RunManifest
from strata.simulation.engine import RunResult


class EvidenceBundle:
    """Creates a self-contained bundle containing experiment definition, event log, and manifest."""

    @classmethod
    def create_bundle(
        cls,
        bundle_dir: Path | str,
        run_result: RunResult,
        experiment_definition_raw: str,
    ) -> Path:
        """Create a complete artifact directory bundle."""
        root = Path(bundle_dir)
        root.mkdir(parents=True, exist_ok=True)

        # 1. Save experiment.yaml
        exp_path = root / "experiment.yaml"
        exp_path.write_text(experiment_definition_raw, encoding="utf-8")

        # 2. Save events.jsonl
        events_path = root / "events.jsonl"
        with JsonlEventLogger(events_path) as logger:
            for event in run_result.events:
                logger.log(event)

        # 3. Save run_summary.json
        summary_path = root / "run_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(run_result.to_dict(), f, indent=2, ensure_ascii=False)

        # 4. Generate manifest with SHA-256 hashes
        manifest = RunManifest(
            run_id=run_result.run_id,
            experiment_id=run_result.experiment_id,
            seed=run_result.seed,
            metadata={
                "status": run_result.status.value,
                "events_processed": run_result.events_processed,
                "final_virtual_time_us": run_result.final_virtual_time_us,
                "all_invariants_passed": run_result.all_invariants_passed,
            },
        )
        manifest.add_artifact("experiment.yaml", exp_path)
        manifest.add_artifact("events.jsonl", events_path)
        manifest.add_artifact("run_summary.json", summary_path)

        manifest_path = root / "manifest.json"
        manifest.write_to(manifest_path)

        return root
