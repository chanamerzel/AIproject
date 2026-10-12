import uuid

from app.event_store import EventStore
from app.queries.applications import get_application, get_application_by_candidate_job
from app.queries.jobs import get_job


def submit_application(job_id: str, candidate_id: str, cv_path: str, cv_text: str) -> str:
    job = get_job(job_id)
    if not job or job["status"] != "Open":
        raise ValueError("ניתן להגיש רק למשרה פתוחה")
    existing = get_application_by_candidate_job(candidate_id, job_id)
    if existing:
        raise ValueError("כבר הגשת מועמדות למשרה זו")
    application_id = str(uuid.uuid4())
    EventStore.append(
        "ApplicationSubmitted",
        "Application",
        application_id,
        {
            "job_id": job_id,
            "candidate_id": candidate_id,
            "cv_path": cv_path,
            "cv_text": cv_text,
        },
        {"user_id": candidate_id},
    )
    EventStore.append(
        "CvEmbedded",
        "Application",
        application_id,
        {"job_id": job_id},
        {"user_id": candidate_id},
    )
    return application_id


def start_screening(application_id: str):
    app_row = get_application(application_id)
    if not app_row:
        raise ValueError("מועמדות לא נמצאה")
    EventStore.append(
        "ApplicationScreeningStarted",
        "Application",
        application_id,
        {},
        {"source": "agent"},
    )


def fail_screening(application_id: str, error: str, final: bool):
    if not get_application(application_id):
        raise ValueError("מועמדות לא נמצאה")
    EventStore.append(
        "ApplicationScreeningFailed",
        "Application",
        application_id,
        {"error": error[:1000], "final": final},
        {"source": "agent"},
    )


def complete_screening(application_id: str, report: dict):
    app_row = get_application(application_id)
    if not app_row:
        raise ValueError("מועמדות לא נמצאה")
    EventStore.append(
        "ApplicationScreeningCompleted",
        "Application",
        application_id,
        report,
        {"source": "agent"},
    )


RESCREENABLE = {"Screened", "ScreeningFailed"}


def request_rescreen(application_id: str, reason: str, actor_id: str):
    app_row = get_application(application_id)
    if not app_row:
        raise ValueError("מועמדות לא נמצאה")
    if app_row["status"] not in RESCREENABLE:
        raise ValueError("אפשר לבקש הערכה חוזרת רק למועמדות שהוערכה או שההערכה שלה נכשלה")
    if not reason.strip():
        raise ValueError("יש לכתוב למה נדרשת הערכה חוזרת")
    EventStore.append(
        "ApplicationRescreenRequested",
        "Application",
        application_id,
        {"reason": reason.strip()[:500], "previous_score": app_row.get("agent_score")},
        {"user_id": actor_id},
    )


def decide(application_id: str, decision: str, reason: str, actor_id: str):
    app_row = get_application(application_id)
    if not app_row:
        raise ValueError("מועמדות לא נמצאה")
    if app_row["status"] not in {"Screened", "Interview"}:
        raise ValueError("ניתן להחליט רק אחרי הערכת הסוכן")
    mapping = {
        "interview": "InterviewScheduled",
        "reject": "ApplicationRejected",
        "offer": "OfferExtended",
    }
    event_type = mapping.get(decision)
    if not event_type:
        raise ValueError("החלטה לא חוקית")
    EventStore.append(
        event_type,
        "Application",
        application_id,
        {"reason": reason},
        {"user_id": actor_id},
    )


def record_email_sent(application_id: str, to_email: str, subject: str):
    EventStore.append(
        "DecisionEmailSent",
        "Application",
        application_id,
        {"to": to_email, "subject": subject},
        {"source": "gmail-mcp"},
    )
