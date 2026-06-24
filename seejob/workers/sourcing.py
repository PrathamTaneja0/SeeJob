"""Scheduled job sourcing worker — cron-style tick, not 24/7 daemon."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from seejob.core.database import SessionLocal
from seejob.services.policy import get_policy_config
from seejob.services.sourcing.pipeline import SourcingRunResult, build_policy_sources, run_sourcing_pipeline
from seejob.workers.base import WorkerResult, WorkerStatus

logger = logging.getLogger(__name__)


async def run_sourcing_tick(
    db: Session,
    *,
    person_id: int | None = None,
) -> SourcingRunResult:
    """Single sourcing pass: poll configured sources and ingest new jobs."""
    policy = get_policy_config(db)
    if not policy.sourcing_enabled:
        return SourcingRunResult(errors=["sourcing disabled in policy"])

    sources = build_policy_sources(policy)
    return await run_sourcing_pipeline(db, sources, person_id=person_id)


async def run_sourcing_worker(
    db: Session | None = None,
    *,
    person_id: int | None = None,
) -> WorkerResult:
    """Execute one sourcing worker run and return structured result."""
    started = datetime.now(UTC)
    owns_session = db is None
    session = db or SessionLocal()

    try:
        result = await run_sourcing_tick(session, person_id=person_id)
        message = (
            f"fetched={result.fetched} created={result.created} "
            f"duplicates={result.duplicates} filtered={result.filtered} "
            f"scored={result.scored} archived={result.archived}"
        )
        if result.errors:
            message += f"; errors={'; '.join(result.errors)}"

        status = WorkerStatus.FAILED if result.errors and result.created == 0 else WorkerStatus.COMPLETED
        return WorkerResult(
            worker_name="sourcing_worker",
            status=status,
            items_processed=result.created,
            message=message,
            started_at=started,
            finished_at=datetime.now(UTC),
        )
    except Exception as exc:
        logger.exception("Sourcing worker failed")
        return WorkerResult(
            worker_name="sourcing_worker",
            status=WorkerStatus.FAILED,
            message=str(exc),
            started_at=started,
            finished_at=datetime.now(UTC),
        )
    finally:
        if owns_session:
            session.close()


def main(argv: list[str] | None = None) -> int:
    """CLI entry: python -m seejob.workers.sourcing [--person-id N]."""
    parser = argparse.ArgumentParser(description="Run one SeeJob sourcing tick")
    parser.add_argument("--person-id", type=int, default=None, help="Score ingested jobs for person")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    result = asyncio.run(run_sourcing_worker(person_id=args.person_id))
    print(result.message or result.status.value)
    return 0 if result.status != WorkerStatus.FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
