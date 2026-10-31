"""Repository for persisting and querying experiment run metadata."""

from __future__ import annotations

import json
from typing import Any
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from strata.simulation.engine import RunResult
from strata.storage.database import DatabaseManager
from strata.storage.models import InvariantRecord, RunRecord


class RunRepository:
    """Relational repository managing persistent run records."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        self.db = db_manager

    def save_run(
        self,
        run_result: RunResult,
        manifest_hash: str | None = None,
    ) -> RunRecord:
        """Persist a completed run result and its invariant records into SQLite."""
        with self.db.session() as session:
            record = RunRecord(
                run_id=run_result.run_id,
                experiment_id=run_result.experiment_id,
                status=run_result.status.value,
                seed=run_result.seed,
                events_processed=run_result.events_processed,
                final_virtual_time_us=run_result.final_virtual_time_us,
                wall_clock_duration_s=run_result.wall_clock_duration_s,
                all_invariants_passed=1 if run_result.all_invariants_passed else 0,
                manifest_hash=manifest_hash,
                summary_json=json.dumps(run_result.to_dict(), ensure_ascii=False),
            )

            for inv in run_result.invariant_results:
                inv_rec = InvariantRecord(
                    run_id=run_result.run_id,
                    invariant_id=inv.invariant_id,
                    invariant_type=inv.invariant_type,
                    verdict=inv.verdict.value,
                    explanation=inv.explanation,
                    details_json=json.dumps(inv.details, ensure_ascii=False),
                )
                record.invariant_records.append(inv_rec)

            merged_record = session.merge(record)
            session.commit()
            return merged_record

    def get_run(self, run_id: str) -> RunRecord | None:
        """Retrieve a run record by run_id."""
        with self.db.session() as session:
            stmt = (
                select(RunRecord)
                .options(selectinload(RunRecord.invariant_records))
                .where(RunRecord.run_id == run_id)
            )
            return session.scalars(stmt).first()

    def list_runs(
        self,
        experiment_id: str | None = None,
        limit: int = 50,
    ) -> list[RunRecord]:
        """List runs ordered by creation timestamp descending."""
        with self.db.session() as session:
            stmt = (
                select(RunRecord)
                .options(selectinload(RunRecord.invariant_records))
                .order_by(desc(RunRecord.created_at))
                .limit(limit)
            )
            if experiment_id:
                stmt = stmt.where(RunRecord.experiment_id == experiment_id)
            return list(session.scalars(stmt).all())
