import uuid

from app.event_store import EventStore
from app.queries.jobs import get_job


def draft_job(created_by: str, title: str, description: str, must_have: str, nice_to_have: str, min_years: int, location: str) -> str:
    if not title or not title.strip():
        raise ValueError("יש להזין כותרת משרה")
    if not description or not description.strip():
        raise ValueError("יש להזין תיאור משרה")
    if not must_have or not must_have.strip():
        raise ValueError("יש להזין כישורי חובה")
    job_id = str(uuid.uuid4())
    EventStore.append(
        "JobDrafted",
        "Job",
        job_id,
        {
            "title": title.strip(),
            "description": description.strip(),
            "must_have_skills": must_have.strip(),
            "nice_to_have_skills": nice_to_have.strip(),
            "min_years": int(min_years or 0),
            "location": location.strip(),
            "created_by": created_by,
        },
        {"user_id": created_by},
    )
    return job_id


def open_job(job_id: str, actor_id: str):
    job = get_job(job_id)
    if not job:
        raise ValueError("משרה לא נמצאה")
    if job["status"] != "Draft":
        raise ValueError("ניתן לפתוח רק משרה בטיוטה")
    EventStore.append("JobOpened", "Job", job_id, {}, {"user_id": actor_id})


def close_job(job_id: str, actor_id: str):
    job = get_job(job_id)
    if not job:
        raise ValueError("משרה לא נמצאה")
    EventStore.append("JobClosed", "Job", job_id, {}, {"user_id": actor_id})
