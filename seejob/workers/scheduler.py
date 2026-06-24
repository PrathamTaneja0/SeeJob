"""Scheduled worker tick — sourcing plus approved pipeline queue (not a 24/7 daemon)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from seejob.core.database import SessionLocal
from seejob.services.events import emit_event
from seejob.services.pipeline import (
    PipelineAction,
    find_pipeline_candidates,
    run_pipeline_for_application,
)
from seejob.services.policy import get_policy_config
from seejob.services.rate_limit import RateLimitExceeded
from seejob.workers.base import WorkerResult, WorkerStatus
from seejob.workers.sourcing import run_sourcing_tick

logger = logging.getLogger(__name__)


@dataclass
class SchedulerTickResult:
    """Structured outcome of one scheduler invocation."""

    sourcing_message: str
    pipeline_processed: int
    pipeline_submitted: int
    pipeline_paused: int
    pipeline_skipped: int
    pipeline_failed: int
    errors: list[str]

    @property
    def summary(self) -> str:
        parts = [
            f"sourcing: {self.sourcing_message}",
            f"pipeline processed={self.pipeline_processed}",
            f"submitted={self.pipeline_submitted}",
            f"paused={self.pipeline_paused}",
            f"skipped={self.pipeline_skipped}",
            f"failed={self.pipeline_failed}",
        ]
        if self.errors:
            parts.append(f"errors={'; '.join(self.errors)}")
        return "; ".join(parts)


async def process_approved_pipeline_queue(
    db: Session,
    *,
    dry_run: bool = False,
) -> SchedulerTickResult:
    """Run pipeline for applications in the approved jobs queue."""
    policy = get_policy_config(db)
    candidates = find_pipeline_candidates(db, policy)

    processed = submitted = paused = skipped = failed = 0
    errors: list[str] = []

    for app in candidates:
        try:
            result = await run_pipeline_for_application(
                db,
                app.id,
                dry_run=dry_run,
            )
        except RateLimitExceeded as exc:
            errors.append(str(exc))
            skipped += 1
            break
        except Exception as exc:
            logger.exception("Pipeline failed for application %s", app.id)
            errors.append(f"app {app.id}: {exc}")
            failed += 1
            continue

        processed += 1
        if result.action == PipelineAction.SUBMITTED:
            submitted += 1
        elif result.action == PipelineAction.PAUSED:
            paused += 1
        elif result.action == PipelineAction.SKIPPED:
            skipped += 1
        elif result.action == PipelineAction.FAILED:
            failed += 1

    return SchedulerTickResult(
        sourcing_message="not run",
        pipeline_processed=processed,
        pipeline_submitted=submitted,
        pipeline_paused=paused,
        pipeline_skipped=skipped,
        pipeline_failed=failed,
        errors=errors,
    )


async def run_scheduled_tick(
    db: Session,
    *,
    person_id: int | None = None,
    dry_run: bool = False,
    skip_sourcing: bool = False,
) -> SchedulerTickResult:
    """Single scheduler tick: sourcing pass then approved pipeline queue."""
    policy = get_policy_config(db)
    errors: list[str] = []

    if skip_sourcing or not policy.sourcing_enabled:
        sourcing_message = "sourcing skipped"
        sourcing_result = None
    else:
        sourcing_result = await run_sourcing_tick(db, person_id=person_id)
        sourcing_message = (
            f"fetched={sourcing_result.fetched} created={sourcing_result.created} "
            f"scored={sourcing_result.scored}"
        )
        if sourcing_result.errors:
            errors.extend(sourcing_result.errors)

    emit_event(
        "scheduler_tick",
        sourcing_message,
        worker_name="scheduler",
        metadata={"sourcing_interval_minutes": policy.sourcing_interval_minutes},
    )

    pipeline_result = await process_approved_pipeline_queue(db, dry_run=dry_run)
    pipeline_result.sourcing_message = sourcing_message
    pipeline_result.errors = errors + pipeline_result.errors

    emit_event(
        "scheduler_complete",
        pipeline_result.summary,
        worker_name="scheduler",
    )

    return pipeline_result


async def run_scheduler_worker(
    db: Session | None = None,
    *,
    person_id: int | None = None,
    dry_run: bool = False,
    skip_sourcing: bool = False,
) -> WorkerResult:
    """Execute one scheduler tick and return structured worker result."""
    started = datetime.now(UTC)
    owns_session = db is None
    session = db or SessionLocal()

    try:
        result = await run_scheduled_tick(
            session,
            person_id=person_id,
            dry_run=dry_run,
            skip_sourcing=skip_sourcing,
        )
        failed_status = (
            WorkerStatus.FAILED
            if result.errors and result.pipeline_processed == 0
            else WorkerStatus.COMPLETED
        )
        return WorkerResult(
            worker_name="scheduler",
            status=failed_status,
            items_processed=result.pipeline_processed,
            message=result.summary,
            started_at=started,
            finished_at=datetime.now(UTC),
        )
    except Exception as exc:
        logger.exception("Scheduler tick failed")
        return WorkerResult(
            worker_name="scheduler",
            status=WorkerStatus.FAILED,
            message=str(exc),
            started_at=started,
            finished_at=datetime.now(UTC),
        )
    finally:
        if owns_session:
            session.close()


def main(argv: list[str] | None = None) -> int:
    """CLI entry: seejob-tick [--person-id N] [--dry-run] [--skip-sourcing]."""
    parser = argparse.ArgumentParser(
        description="Run one SeeJob scheduler tick (sourcing + pipeline queue)"
    )
    parser.add_argument(
        "--person-id", type=int, default=None, help="Score ingested jobs for person"
    )
    parser.add_argument("--dry-run", action="store_true", help="Apply without submitting forms")
    parser.add_argument("--skip-sourcing", action="store_true", help="Only process pipeline queue")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    result = asyncio.run(
        run_scheduler_worker(
            person_id=args.person_id,
            dry_run=args.dry_run,
            skip_sourcing=args.skip_sourcing,
        )
    )
    print(result.message or result.status.value)
    return 0 if result.status != WorkerStatus.FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
