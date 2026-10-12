from io import BytesIO
from pathlib import Path

from tests.conftest import login, logout, open_python_job, register


def _cv_file(name="cv_python.txt"):
    data = Path("samples") / name
    return (BytesIO(data.read_bytes()), name)


def test_apply_increments_applicant_count(app, client):
    job_id = open_python_job(client)
    register(client, "c@x.test", "candidate")
    response = client.post(
        f"/applications/apply/{job_id}",
        data={"cv": _cv_file()},
        follow_redirects=True,
    )
    assert response.status_code == 200
    from app.queries.jobs import get_job

    with app.app_context():
        job = get_job(job_id)
        from app.db import fetch_one

        event = fetch_one(
            "SELECT event_type FROM events WHERE event_type = ?",
            ("ApplicationSubmitted",),
        )
    assert job["applicant_count"] == 1
    assert event is not None


def test_dashboard_counts_open_jobs_and_applicants(client):
    job_id = open_python_job(client)
    register(client, "c@x.test", "candidate")
    client.post(
        f"/applications/apply/{job_id}",
        data={"cv": _cv_file()},
        follow_redirects=True,
    )
    logout(client)
    login(client, "hr@x.test")
    dash = client.get("/dashboard/")
    html = dash.get_data(as_text=True)
    assert "Python Backend" in html
    assert "1" in html
