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


def _draft_named(client, title, location):
    page = client.post(
        "/jobs/new",
        data={
            "title": title,
            "description": "Flask APIs",
            "must_have_skills": "Python",
            "nice_to_have_skills": "",
            "min_years": "1",
            "location": location,
        },
        follow_redirects=True,
    )
    return page.request.path.split("/")[-1]


def test_job_cards_page_open_jobs_without_table(client, monkeypatch):
    monkeypatch.setattr("app.views.jobs.JOBS_PAGE_SIZE", 1)
    open_python_job(client)
    login(client, "hr@x.test")
    second = _draft_named(client, "Data Engineer", "Haifa")
    logout(client)
    login(client, "hm@x.test")
    client.post(f"/jobs/{second}/open", follow_redirects=True)
    logout(client)
    login(client, "hr@x.test")
    _draft_named(client, "Hidden Draft", "Remote")
    logout(client)

    register(client, "c@x.test", "candidate")
    first = client.get("/jobs/").get_data(as_text=True)
    assert "<table" not in first
    assert "טבלת משרות" not in first
    assert 'name="status"' not in first
    assert ">2</strong> משרות פתוחות" in first
    assert first.index("job-grid") < first.index("jobs-pages")
    assert 'aria-current="page">1<' in first
    assert "page=2" in first
    assert "Data Engineer" in first
    assert "Python Backend" not in first
    assert "Hidden Draft" not in first

    second_page = client.get("/jobs/?page=2").get_data(as_text=True)
    assert "Python Backend" in second_page
    assert "Data Engineer" not in second_page
    assert 'aria-current="page">2<' in second_page

    logout(client)
    login(client, "hr@x.test")
    staff = client.get("/jobs/").get_data(as_text=True)
    assert ">2</strong> משרות פתוחות" in staff
    assert "Hidden Draft" not in staff
    assert "כל הסטטוסים" not in staff
