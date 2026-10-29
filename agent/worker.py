"""Independent process: reads the database, screens applications, emails HR decisions, writes events."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
os.environ.setdefault("CHROMA_PATH", str(ROOT / "chroma_data"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fitscreen.worker")

MAX_ATTEMPTS = 3
_app = None


def _runtime_app():
    """One process-wide app. A caller that already has an app context keeps that database."""
    global _app
    from flask import current_app, has_app_context

    if has_app_context():
        return current_app._get_current_object()
    if _app is None:
        from app import create_app

        _app = create_app()
    return _app


def _preflight() -> str | None:
    """Return a reason not to screen, or None. Checked before any application is touched."""
    from agent.deep_agent import AgentNotConfigured, agent_mode, model_chain

    if agent_mode() == "pipeline":
        return None
    try:
        chain = model_chain()
    except AgentNotConfigured as exc:
        return str(exc)
    logger.info("models available: %s", ", ".join(name for name, _ in chain))
    return None


def _previous_failures(application_id: str) -> int:
    """Failed attempts since the last re-screen request (a re-screen gives a fresh set of attempts)."""
    from app import db

    rows = db.fetch_all(
        """SELECT event_type FROM events
           WHERE aggregate_id = ?
             AND event_type IN ('ApplicationRescreenRequested', 'ApplicationScreeningFailed')
           ORDER BY version ASC""",
        (application_id,),
    )
    failures = 0
    for event in rows:
        if event["event_type"] == "ApplicationRescreenRequested":
            failures = 0
        else:
            failures += 1
    return failures


def requeue_abandoned(older_than_seconds: int = 600) -> int:
    """A screening left in progress (the worker stopped) goes back to the queue."""
    from datetime import datetime, timedelta, timezone

    from app import db
    from app.commands.applications import fail_screening

    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=older_than_seconds)).isoformat()
    rows = db.fetch_all("SELECT id FROM applications WHERE status = 'Screening'")
    moved = 0
    for row in rows:
        started = db.fetch_one(
            """SELECT MAX(occurred_at) AS started FROM events
               WHERE aggregate_id = ? AND event_type = 'ApplicationScreeningStarted'""",
            (row["id"],),
        )
        when = (started or {}).get("started") or ""
        if older_than_seconds > 0 and when > cutoff:
            continue
        fail_screening(row["id"], "screening stopped before it finished", False)
        moved += 1
    return moved


def screen_pending() -> int:
    from agent.deep_agent import describe_runtime, evaluate_application
    from agent.rag import embed_application
    from app.commands.applications import complete_screening, fail_screening, start_screening
    from app.db import hold_connection
    from app.queries.applications import pending_screening

    app = _runtime_app()
    processed = 0
    with app.app_context(), hold_connection():
        # Anything still "in progress" belongs to a worker that already stopped.
        requeue_abandoned(older_than_seconds=0)
        rows = pending_screening()
        if not rows:
            return 0
        blocked = _preflight()
        if blocked:
            logger.error("%s application(s) waiting, not screening: %s", len(rows), blocked)
            return 0
        for row in rows:
            try:
                start_screening(row["id"])
                from app.cv_text import enrich_stored_text

                row["cv_text"] = enrich_stored_text(row.get("cv_text") or "", row.get("cv_path"))
                embed_application(row["id"], row["job_id"], row["cv_text"] or "")
                report = evaluate_application(row)
                complete_screening(row["id"], report)
                processed += 1
                logger.info(
                    "screened %s score=%s rec=%s runtime=%s skipped=%s",
                    row["id"],
                    report.get("overall_score"),
                    report.get("recommendation"),
                    report.get("runtime"),
                    report.get("tools_skipped_by_agent"),
                )
            except Exception as exc:
                logger.exception("failed screening %s (%s)", row.get("id"), describe_runtime())
                final = _previous_failures(row["id"]) + 1 >= MAX_ATTEMPTS
                fail_screening(row["id"], f"{type(exc).__name__}: {exc}", final)
    return processed


def main(argv=None) -> int:
    from agent.deep_agent import describe_runtime
    from agent.notifier import notify_pending

    parser = argparse.ArgumentParser(description="FitScreen screening worker — reads DB")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    seconds = int(os.getenv("WORKER_POLL_SECONDS", "20"))
    logger.info("agent runtime: %s", describe_runtime())
    app = _runtime_app()
    with app.app_context():
        if args.once:
            logger.info("sent %s decision emails", notify_pending())
            logger.info("processed %s applications", screen_pending())
            return 0
        logger.info("worker reading database every %ss", seconds)
        while True:
            # Emails first: a screening can take minutes and should not delay a decision email.
            for step in (notify_pending, screen_pending):
                try:
                    step()
                except Exception:
                    logger.exception("%s failed", step.__name__)
            time.sleep(seconds)


if __name__ == "__main__":
    sys.exit(main())
