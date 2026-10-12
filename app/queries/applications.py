from app import db


def get_application(application_id: str):
    return db.fetch_one(
        """SELECT a.*, j.title AS job_title, j.description AS job_description,
                  j.must_have_skills, j.nice_to_have_skills, j.min_years, j.location AS job_location,
                  u.full_name AS candidate_name, u.email AS candidate_email
           FROM applications a
           JOIN jobs j ON j.id = a.job_id
           JOIN users u ON u.id = a.candidate_id
           WHERE a.id = ?""",
        (application_id,),
    )


def get_application_by_candidate_job(candidate_id: str, job_id: str):
    return db.fetch_one(
        "SELECT * FROM applications WHERE candidate_id = ? AND job_id = ?",
        (candidate_id, job_id),
    )


def list_for_job(job_id: str, status=None):
    sql = """SELECT a.*, u.full_name AS candidate_name, u.email AS candidate_email
             FROM applications a
             JOIN users u ON u.id = a.candidate_id
             WHERE a.job_id = ?"""
    params = [job_id]
    if status:
        sql += " AND a.status = ?"
        params.append(status)
    sql += " ORDER BY COALESCE(a.agent_score, -1) DESC, u.full_name"
    return db.fetch_all(sql, tuple(params))


def list_for_candidate(candidate_id: str):
    return db.fetch_all(
        """SELECT a.*, j.title AS job_title, j.status AS job_status
           FROM applications a JOIN jobs j ON j.id = a.job_id
           WHERE a.candidate_id = ? ORDER BY j.title""",
        (candidate_id,),
    )


def pending_screening():
    return db.fetch_all(
        """SELECT a.*, j.title AS job_title, j.description AS job_description,
                  j.must_have_skills, j.nice_to_have_skills, j.min_years, j.location AS job_location
           FROM applications a JOIN jobs j ON j.id = a.job_id
           WHERE a.status = 'Submitted'"""
    )
