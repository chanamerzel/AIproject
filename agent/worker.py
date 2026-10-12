"""Independent process: reads applications from the database, screens, writes events."""

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


def _preflight() -> str | None:
    """Return a reason not to screen, or None. Checked before any application is touched."""
    from agent.deep_agent import AgentNotConfigured, _build_model, agent_mode

    if agent_mode() == "pipeline":
        return None
    try:
        _build_model()
    except AgentNotConfigured as exc:
        return str(exc)
    return None


def _previous_failures(application_id: str) -> int:
    from app.event_store import EventStore

    return sum(
        1 for e in EventStore.for_aggregate(application_id) if e["event_type"] == "ApplicationScreeningFailed"
    )


def screen_pending() -> int:
    from agent.deep_agent import describe_runtime, evaluate_application
    from agent.rag import embed_application
    from app import create_app
    from app.commands.applications import complete_screening, fail_screening, start_screening
    from app.queries.applications import get_application, pending_screening

    app = create_app()
    processed = 0
    with app.app_context():
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
                detail = get_application(row["id"])
                embed_application(detail["id"], detail["job_id"], detail["cv_text"] or "")
                report = evaluate_application(detail)
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

    parser = argparse.ArgumentParser(description="FitScreen screening worker — reads DB")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    seconds = int(os.getenv("WORKER_POLL_SECONDS", "20"))
    logger.info("agent runtime: %s", describe_runtime())
    if args.once:
        n = screen_pending()
        logger.info("processed %s applications", n)
        return 0
    logger.info("worker reading database every %ss", seconds)
    while True:
        try:
            screen_pending()
        except Exception:
            logger.exception("poll failed")
        time.sleep(seconds)


if __name__ == "__main__":
    sys.exit(main())
