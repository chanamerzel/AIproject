from tests.conftest import login, logout, open_python_job, register


def _draft(client):
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
    return page, page.request.path.split("/")[-1]


def test_hr_drafts_and_hiring_manager_opens(client):
    register(client, "hr@x.test", "hr")
    page, job_id = _draft(client)
    assert "טיוטה" in page.get_data(as_text=True)
    assert client.post(f"/jobs/{job_id}/open").status_code == 403
    logout(client)

    register(client, "hm@x.test", "hiring_manager")
    opened = client.post(f"/jobs/{job_id}/open", follow_redirects=True)
    assert opened.status_code == 200
    assert "פתוחה" in opened.get_data(as_text=True)


def test_hiring_manager_cannot_draft_or_decide(client):
    register(client, "hm@x.test", "hiring_manager")
    assert client.get("/jobs/new").status_code == 403
    assert client.post("/applications/any/decide", data={"decision": "reject"}).status_code == 403
    assert client.post("/applications/any/rescreen", data={"reason": "x"}).status_code == 403


def test_only_hiring_manager_closes(client):
    job_id = open_python_job(client)
    login(client, "hr@x.test")
    assert client.post(f"/jobs/{job_id}/close").status_code == 403
    logout(client)
    login(client, "hm@x.test")
    closed = client.post(f"/jobs/{job_id}/close", follow_redirects=True)
    assert "סגורה" in closed.get_data(as_text=True)


def test_search_finds_open_job(client):
    open_python_job(client)
    register(client, "c@x.test", "candidate")
    found = client.get("/jobs/?q=Flask")
    assert "Python Backend" in found.get_data(as_text=True)
