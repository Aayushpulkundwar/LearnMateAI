"""Explicit, identity-gated retries of failed or stale pending uploads."""
import argparse
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import select, text
from app.core.config import settings
from app.core.db import SyncSessionLocal
from app.models.document import Document
from app.tasks.ingestion import ingest_document_task


def retryable_document(row, now=None):
    """Only explicit failed or long-unclaimed pending uploads may be retried.

    Active processing is never restarted based on an elapsed clock. The worker's
    existing advisory lock remains the final protection against duplicate work.
    """
    if row.processing_status == 'failed':
        return True
    if row.processing_status != 'pending':
        return False
    timestamp = row.heartbeat_at or row.created_at
    return timestamp is not None and timestamp < (now or datetime.now(timezone.utc)) - timedelta(minutes=15)


def retry_sequential(document_ids, *, dispatch=None, timeout=900):
    """Wait for each terminal task result before sending another retry.

    A result timeout aborts this loop: it does not cancel the task, and another
    extraction must not start on the assumption that the previous one stopped.
    """
    dispatch = dispatch or ingest_document_task.delay
    failures = []
    for document_id in document_ids:
        result = dispatch(str(document_id))
        print("Queued", str(document_id), "task", result.id)
        outcome = result.get(timeout=timeout, propagate=False)
        if isinstance(outcome, BaseException) or not isinstance(outcome, dict) or outcome.get("status") != "completed":
            failures.append(str(document_id))
            print("Retry did not complete:", str(document_id))
        else:
            print("Completed", str(document_id), "chunks", outcome.get("chunks_count", "unchanged"))
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document_ids", nargs="+", type=UUID)
    parser.add_argument("--wait-timeout", type=int, default=900, help="Seconds to wait per complete ingestion job; abort if exceeded.")
    args = parser.parse_args()
    if settings.ENVIRONMENT.lower() not in {"development", "local", "staging"}:
        raise RuntimeError("Retries restricted to local/staging.")
    with SyncSessionLocal() as session:
        print("Database identity:", session.execute(text("SELECT current_database(), current_user")).one())
        rows = session.scalars(select(Document).where(Document.id.in_(args.document_ids))).all()
        if len(rows) != len(set(args.document_ids)):
            raise RuntimeError("Some selected documents are missing; no retries queued.")
        for row in rows:
            print(str(row.id), row.chapter, row.processing_status)
        failed = [row for row in rows if retryable_document(row)]
        if not failed:
            print("No selected failed or stale pending documents; no retries queued.")
            return
        if input("Type RETRY_FAILED to confirm this environment and queue only failed/stale pending documents: ") != "RETRY_FAILED":
            raise RuntimeError("Retry cancelled.")
        failures = retry_sequential([row.id for row in failed], timeout=args.wait_timeout)
        if failures:
            raise RuntimeError("Some documents remain incomplete: " + ", ".join(failures))


if __name__ == "__main__":
    main()
