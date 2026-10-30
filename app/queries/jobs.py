from app import db


def get_job(job_id: str):
    return db.fetch_one("SELECT * FROM jobs WHERE id = ?", (job_id,))


def _job_filters(status=None, q=None):
    sql = ""
    params = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if q:
        like = f"%{q}%"
        sql += " AND (title LIKE ? OR description LIKE ? OR must_have_skills LIKE ? OR location LIKE ?)"
        params.extend([like, like, like, like])
    return sql, params


def count_jobs(status=None, q=None):
    where, params = _job_filters(status, q)
    row = db.fetch_one(f"SELECT COUNT(*) AS n FROM jobs WHERE 1=1{where}", tuple(params))
    return int(row["n"]) if row else 0


def list_jobs(status=None, q=None, limit=None, offset=0):
    where, params = _job_filters(status, q)
    sql = (
        "SELECT id, title, location, status, min_years, applicant_count "
        f"FROM jobs WHERE 1=1{where} ORDER BY title, id"
    )
    page_params = list(params)
    if limit is not None:
        if db.backend_name() == "mssql":
            sql += " OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
            page_params.extend([offset, limit])
        else:
            sql += " LIMIT ? OFFSET ?"
            page_params.extend([limit, offset])
    return db.fetch_all(sql, tuple(page_params))


def dashboard_rows(limit=None, offset=0):
    sql = (
        "SELECT id, title, status, location, applicant_count, opened_at "
        "FROM jobs WHERE status = 'Open' ORDER BY applicant_count DESC, title, id"
    )
    params = []
    if limit is not None:
        if db.backend_name() == "mssql":
            sql += " OFFSET ? ROWS FETCH NEXT ? ROWS ONLY"
            params.extend([offset, limit])
        else:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
    return db.fetch_all(sql, tuple(params))


def application_status_counts():
    rows = db.fetch_all(
        "SELECT status, COUNT(*) AS n FROM applications GROUP BY status"
    )
    return {r["status"]: r["n"] for r in rows}
