"""Decision emails: each HR decision is emailed to the candidate once, through the Gmail MCP server.

Runs inside the agent.worker loop (or once with `python -m agent.notifier`), never in a Flask request.
"""

from __future__ import annotations

import argparse
import html
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

logger = logging.getLogger("fitscreen.notifier")

SUBJECTS = {
    "interview": "הזמנה לראיון: {job}",
    "offer": "הצעת עבודה: {job}",
    "reject": "עדכון לגבי מועמדותך למשרת {job}",
}
OPENINGS = {
    "interview": "שמחים לעדכן שהחלטנו להזמין אותך לראיון למשרת {job}.",
    "offer": "שמחים לבשר שהחלטנו להציע לך את משרת {job}.",
    "reject": "תודה על התעניינותך במשרת {job}. לאחר בחינת המועמדות החלטנו שלא להתקדם בשלב זה.",
}
CLOSINGS = {
    "interview": "צוות הגיוס ייצור איתך קשר בימים הקרובים לתיאום מועד.",
    "offer": "צוות הגיוס ייצור איתך קשר בימים הקרובים להמשך התהליך.",
    "reject": "נשמח לשמור על קשר לגבי משרות מתאימות בעתיד.",
}

_last_skip: tuple | None = None
_app = None


def compose_email(item: dict) -> tuple[str, str, str]:
    """Deterministic Hebrew subject, plain-text body and RTL HTML body for one decision."""
    decision, job = item["decision"], item["job_title"]
    subject = SUBJECTS[decision].format(job=job)
    lines = [f"שלום {item['candidate_name']},", "", OPENINGS[decision].format(job=job)]
    if item.get("reason"):
        lines += ["", f"דברי צוות הגיוס: {item['reason']}"]
    lines += ["", CLOSINGS[decision], "", "בברכה,", "צוות הגיוס, FitScreen"]
    text = "\n".join(lines)
    paragraphs = "".join(f"<p>{html.escape(line)}</p>" if line else "" for line in lines)
    return subject, text, f'<div dir="rtl" style="text-align:right">{paragraphs}</div>'


def _retry_due(item: dict) -> bool:
    if item["status"] != "failed" or not item.get("last_failed_at"):
        return True
    wait = int(os.getenv("EMAIL_RETRY_SECONDS", "300"))
    last = datetime.fromisoformat(item["last_failed_at"])
    return (datetime.now(timezone.utc) - last).total_seconds() >= wait


def send_pending_emails() -> int:
    """Send every open decision email. Needs an app context. Returns how many were sent."""
    global _last_skip
    from agent import mcp_client
    from app.commands.applications import record_email_failed, record_email_sent
    from app.queries.notifications import pending_decision_emails

    items = [item for item in pending_decision_emails() if _retry_due(item)]
    if not items:
        return 0
    missing = mcp_client.gmail_not_configured()
    if missing:
        if _last_skip != (len(items), missing):
            logger.info("%s decision email(s) waiting, Gmail MCP not configured: %s", len(items), missing)
            _last_skip = (len(items), missing)
        return 0
    _last_skip = None
    sent = 0
    for item in items:
        subject, text, html_body = compose_email(item)
        result = mcp_client.call_gmail_send(item["candidate_email"], subject, text, html_body)
        try:
            if result["ok"]:
                record_email_sent(
                    item["application_id"],
                    item["decision_event_id"],
                    item["candidate_email"],
                    subject,
                    result["message_id"],
                )
                sent += 1
                logger.info("decision email sent %s -> %s id=%s", item["decision"], item["candidate_email"], result["message_id"])
            else:
                record_email_failed(item["application_id"], item["decision_event_id"], item["candidate_email"], result["error"])
                logger.warning("decision email failed %s -> %s: %s", item["decision"], item["candidate_email"], result["error"])
        except Exception:
            logger.exception("could not record the email outcome for decision %s (gmail ok=%s)", item["decision_event_id"], result["ok"])
    return sent


def notify_pending() -> int:
    global _app
    from app import create_app

    if _app is None:
        _app = create_app()
    with _app.app_context():
        return send_pending_emails()


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    argparse.ArgumentParser(description="Send pending FitScreen decision emails through Gmail MCP once").parse_args(argv)
    logger.info("sent %s decision email(s)", notify_pending())
    return 0


if __name__ == "__main__":
    sys.exit(main())
