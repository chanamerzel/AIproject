from app import db


def get_job(job_id: str):
    return db.fetch_one("SELECT * FROM jobs WHERE id = ?", (job_id,))


def list_jobs(status=None, q=None):
    sql = "SELECT id, title, location, status, min_years, applicant_count FROM jobs WHERE 1=1"
    params = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if q:
        like = f"%{q}%"
        sql += " AND (title LIKE ? OR description LIKE ? OR must_have_skills LIKE ? OR location LIKE ?)"
        params.extend([like, like, like, like])
    sql += " ORDER BY title"
    return db.fetch_all(sql, tuple(params))


def dashboard_rows():
    return db.fetch_all(
        """SELECT id, title, status, location, applicant_count, opened_at
           FROM jobs WHERE status = 'Open' ORDER BY applicant_count DESC, title"""
    )


def application_status_counts():
    rows = db.fetch_all(
        "SELECT status, COUNT(*) AS n FROM applications GROUP BY status"
    )
    return {r["status"]: r["n"] for r in rows}
