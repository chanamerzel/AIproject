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


def _open_named(client, title):
    login(client, "hr@x.test")
    page = client.post(
        "/jobs/new",
        data={
            "title": title,
            "description": "Flask APIs",
            "must_have_skills": "Python",
            "nice_to_have_skills": "",
            "min_years": "1",
            "location": "Haifa",
        },
        follow_redirects=True,
    )
    job_id = page.request.path.split("/")[-1]
    logout(client)
    login(client, "hm@x.test")
    client.post(f"/jobs/{job_id}/open", follow_redirects=True)
    logout(client)


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


def test_dashboard_table_pages_without_changing_totals(client, monkeypatch):
    monkeypatch.setattr("app.views.dashboard.DASHBOARD_PAGE_SIZE", 1)
    open_python_job(client)
    _open_named(client, "Data Engineer")
    login(client, "hr@x.test")

    first = client.get("/dashboard/").get_data(as_text=True)
    table = first.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    assert "Data Engineer" in table
    assert "Python Backend" not in table
    assert ">2</div>" in first
    assert "Python Backend" in first
    assert 'aria-current="page">1<' in first
    assert "page=2" in first

    second = client.get("/dashboard/?page=2").get_data(as_text=True)
    table = second.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    assert "Python Backend" in table
    assert "Data Engineer" not in table
    assert ">2</div>" in second
    assert 'aria-current="page">2<' in second
