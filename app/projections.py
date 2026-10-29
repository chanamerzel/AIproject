import json

from app import db


def apply_event(event: dict, payload: dict | None = None):
    if payload is None:
        raw = event["payload_json"]
        payload = json.loads(raw) if isinstance(raw, str) else raw
    etype = event["event_type"]
    handlers = {
        "UserRegistered": _user_registered,
        "JobDrafted": _job_drafted,
        "JobOpened": _job_opened,
        "JobClosed": _job_closed,
        "ApplicationSubmitted": _application_submitted,
        "CvEmbedded": _cv_embedded,
        "ApplicationScreeningStarted": _screening_started,
        "ApplicationScreeningCompleted": _screening_completed,
        "ApplicationScreeningFailed": _screening_failed,
        "ApplicationRescreenRequested": _rescreen_requested,
        "InterviewScheduled": _status,
        "ApplicationRejected": _rejected,
        "OfferExtended": _offer,
        "JobClosureAnnounced": _email_outcome,
        "DecisionEmailSent": _email_outcome,
        "DecisionEmailFailed": _email_outcome,
    }
    handler = handlers.get(etype)
    if handler:
        handler(event, payload)


def _user_registered(event, payload):
    db.execute(
        """INSERT INTO users (id, email, password_hash, full_name, role, auth_provider)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            event["aggregate_id"],
            payload["email"],
            payload["password_hash"],
            payload["full_name"],
            payload["role"],
            payload.get("auth_provider", "password"),
        ),
    )


def _job_drafted(event, payload):
    db.execute(
        """INSERT INTO jobs (id, title, description, must_have_skills, nice_to_have_skills,
           min_years, location, status, created_by, applicant_count, opened_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'Draft', ?, 0, NULL)""",
        (
            event["aggregate_id"],
            payload["title"],
            payload["description"],
            payload["must_have_skills"],
            payload["nice_to_have_skills"],
            payload["min_years"],
            payload["location"],
            payload["created_by"],
        ),
    )


def _job_opened(event, payload):
    db.execute(
        "UPDATE jobs SET status = 'Open', opened_at = ? WHERE id = ?",
        (event["occurred_at"], event["aggregate_id"]),
    )


def _job_closed(event, payload):
    db.execute("UPDATE jobs SET status = 'Closed' WHERE id = ?", (event["aggregate_id"],))


def _application_submitted(event, payload):
    db.execute(
        """INSERT INTO applications (id, job_id, candidate_id, status, cv_path, cv_text,
           agent_score, agent_report_json, decision_reason)
           VALUES (?, ?, ?, 'Submitted', ?, ?, NULL, NULL, NULL)""",
        (
            event["aggregate_id"],
            payload["job_id"],
            payload["candidate_id"],
            payload.get("cv_path"),
            payload.get("cv_text"),
        ),
    )
    db.execute(
        "UPDATE jobs SET applicant_count = applicant_count + 1 WHERE id = ?",
        (payload["job_id"],),
    )


def _cv_embedded(event, payload):
    return


def _screening_started(event, payload):
    db.execute(
        "UPDATE applications SET status = 'Screening' WHERE id = ?",
        (event["aggregate_id"],),
    )


def _screening_completed(event, payload):
    db.execute(
        """UPDATE applications SET status = 'Screened', agent_score = ?, agent_report_json = ?
           WHERE id = ?""",
        (payload.get("overall_score"), json.dumps(payload, ensure_ascii=False), event["aggregate_id"]),
    )


def _screening_failed(event, payload):
    # Non-final failures return the application to the queue so the worker retries it.
    status = "ScreeningFailed" if payload.get("final") else "Submitted"
    db.execute(
        "UPDATE applications SET status = ? WHERE id = ?",
        (status, event["aggregate_id"]),
    )


def _rescreen_requested(event, payload):
    # Back to the worker's queue; the previous report stays until the new one replaces it.
    db.execute(
        "UPDATE applications SET status = 'Submitted' WHERE id = ?",
        (event["aggregate_id"],),
    )


def _status(event, payload):
    db.execute(
        "UPDATE applications SET status = 'Interview', decision_reason = ? WHERE id = ?",
        (payload.get("reason"), event["aggregate_id"]),
    )


def _rejected(event, payload):
    db.execute(
        "UPDATE applications SET status = 'Rejected', decision_reason = ? WHERE id = ?",
        (payload.get("reason"), event["aggregate_id"]),
    )


def _offer(event, payload):
    db.execute(
        "UPDATE applications SET status = 'Offered', decision_reason = ? WHERE id = ?",
        (payload.get("reason"), event["aggregate_id"]),
    )


def _email_outcome(event, payload):
    # No read-model table: app/queries/notifications.py derives email status from the event stream.
    return
