"""F9 candidate ranking and F10 re-screen with screening history."""

from io import BytesIO
from pathlib import Path

import pytest

from agent.rag import embed_application
from agent.worker import _previous_failures
from app.commands.applications import complete_screening, fail_screening, request_rescreen, start_screening
from app.event_store import EventStore
from app.queries.applications import get_application, list_for_job, screening_history
from app.queries.jobs import get_job
from app.queries.ranking import ranking_for_job
from tests.conftest import login, logout, open_python_job, register


def _apply(client, job_id, path):
    path = Path(path)
    register(client, f"{path.stem}@x.test", "candidate", path.stem)
    client.post(
        f"/applications/apply/{job_id}",
        data={"cv": (BytesIO(path.read_bytes()), path.name)},
        follow_redirects=True,
    )
    logout(client)


def _report(score, recommendation, gaps=()):
    return {
        "overall_score": score,
        "skill_coverage": score,
        "semantic_fit": score,
        "web_score": None,
        "recommendation": recommendation,
        "strengths": [],
        "gaps": list(gaps),
        "web_evidence": [],
        "cv_excerpts": [],
        "runtime": "test",
    }


def _screen(application_id, score, recommendation, gaps=()):
    start_screening(application_id)
    complete_screening(application_id, _report(score, recommendation, gaps))


def _rows_by_name(job_id):
    return {row["candidate_name"]: row for row in list_for_job(job_id)}


def test_ranking_orders_screened_by_score_then_unscreened_by_similarity(app, client):
    job_id = open_python_job(client)
    for cv in ("samples/cv_python.txt", "samples/cv_unrelated.txt"):
        _apply(client, job_id, cv)
    register(client, "late@x.test", "candidate", "late")
    client.post(
        f"/applications/apply/{job_id}",
        data={"cv": (BytesIO(Path("samples/cv_python.txt").read_bytes()), "late.txt")},
        follow_redirects=True,
    )
    logout(client)
    with app.app_context():
        rows = _rows_by_name(job_id)
        for row in rows.values():
            embed_application(row["id"], job_id, row["cv_text"])
        _screen(rows["cv_unrelated"]["id"], 30, "reject", ["Missing must-have: Flask"])
        _screen(rows["cv_python"]["id"], 82, "advance")
        ranking = ranking_for_job(get_job(job_id))

    names = [item["candidate_name"] for item in ranking["items"]]
    assert names == ["cv_python", "cv_unrelated", "late"]
    assert [item["rank"] for item in ranking["items"]] == [1, 2, 3]
    assert ranking["screened"] == 2 and ranking["total"] == 3
    assert ranking["summary"] == {"advance": 1, "hold": 0, "reject": 1}
    assert ranking["items"][2]["overall_score"] is None
    assert ranking["items"][2]["semantic_live"] is not None
    assert ranking["items"][1]["missing_skills"] == ["Missing must-have: Flask"]


def test_ranking_page_is_staff_only(app, client):
    job_id = open_python_job(client)
    _apply(client, job_id, "samples/cv_python.txt")
    login(client, "cv_python@x.test")
    assert client.get(f"/jobs/{job_id}/ranking").status_code in (302, 403)
    logout(client)
    login(client, "hr@x.test")
    page = client.get(f"/jobs/{job_id}/ranking")
    assert page.status_code == 200
    assert "cv_python" in page.get_data(as_text=True)


def test_rescreen_appends_event_requeues_and_keeps_history(app, client):
    job_id = open_python_job(client)
    _apply(client, job_id, "samples/cv_python.txt")
    with app.app_context():
        application_id = list_for_job(job_id)[0]["id"]
        _screen(application_id, 60, "hold")

    login(client, "hr@x.test")
    client.post(
        f"/applications/{application_id}/rescreen",
        data={"reason": "Job requirements updated"},
        follow_redirects=True,
    )

    with app.app_context():
        assert get_application(application_id)["status"] == "Submitted"
        _screen(application_id, 75, "advance")
        events = EventStore.for_aggregate(application_id)
        history = screening_history(application_id, events)
        types = [e["event_type"] for e in events]

    assert types.count("ApplicationScreeningCompleted") == 2
    assert "ApplicationRescreenRequested" in types
    assert [h["kind"] for h in history] == ["screened", "rescreen", "screened"]
    assert history[0]["overall_score"] == 60
    assert history[2]["overall_score"] == 75 and history[2]["delta"] == 15
    page = client.get(f"/applications/{application_id}").get_data(as_text=True)
    assert "היסטוריית הערכות" in page and "Job requirements updated" in page


def test_rescreen_rules(app, client):
    job_id = open_python_job(client)
    _apply(client, job_id, "samples/cv_python.txt")
    with app.app_context():
        application_id = list_for_job(job_id)[0]["id"]
        with pytest.raises(ValueError):
            request_rescreen(application_id, "too early", "hr")
        _screen(application_id, 50, "hold")
        with pytest.raises(ValueError):
            request_rescreen(application_id, "  ", "hr")

    login(client, "cv_python@x.test")
    client.post(f"/applications/{application_id}/rescreen", data={"reason": "please"})
    with app.app_context():
        assert get_application(application_id)["status"] == "Screened"


def test_rescreen_gives_failed_application_fresh_attempts(app, client):
    job_id = open_python_job(client)
    _apply(client, job_id, "samples/cv_python.txt")
    with app.app_context():
        application_id = list_for_job(job_id)[0]["id"]
        for attempt in range(3):
            start_screening(application_id)
            fail_screening(application_id, "LLM timeout", final=attempt == 2)
        assert get_application(application_id)["status"] == "ScreeningFailed"
        assert _previous_failures(application_id) == 3
        request_rescreen(application_id, "Gemini key fixed", "hr")
        assert get_application(application_id)["status"] == "Submitted"
        assert _previous_failures(application_id) == 0
