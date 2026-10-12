from tests.conftest import logout, open_python_job, register


def test_hr_creates_draft_only_manager_opens(client):
    register(client, "hr@x.test", "hr")
    page = client.post(
        "/jobs/new",
        data={
            "title": "Python Backend",
            "description": "Flask APIs",
            "must_have_skills": "Python, Flask",
            "nice_to_have_skills": "",
            "min_years": "0",
            "location": "Haifa",
        },
        follow_redirects=True,
    )
    html = page.get_data(as_text=True)
    assert "טיוטה" in html
    job_id = page.request.path.split("/")[-1]
    forbidden = client.post(f"/jobs/{job_id}/open", follow_redirects=True)
    assert forbidden.status_code == 403
    logout(client)
    register(client, "hm@x.test", "hiring_manager")
    opened = client.post(f"/jobs/{job_id}/open", follow_redirects=True)
    assert "פתוחה" in opened.get_data(as_text=True)


def test_search_finds_open_job(client):
    open_python_job(client)
    register(client, "c@x.test", "candidate")
    found = client.get("/jobs/?q=Flask")
    assert "Python Backend" in found.get_data(as_text=True)
