"""F8 decision emails: HR decides in Flask, the worker sends through Gmail MCP once and records the outcome."""

from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent import mcp_client
from agent.notifier import compose_email, send_pending_emails
from app.commands.applications import complete_screening, record_email_sent, start_screening
from app.event_store import EventStore
from app.queries.applications import list_for_job
from app.queries.notifications import pending_decision_emails
from tests.conftest import login, logout, open_python_job, register

REPORT = {
    "overall_score": 80,
    "skill_coverage": 80,
    "semantic_fit": 80,
    "web_score": None,
    "recommendation": "advance",
    "strengths": [],
    "gaps": [],
    "web_evidence": [],
    "cv_excerpts": [],
    "runtime": "test",
}


@pytest.fixture()
def gmail(tmp_path, monkeypatch):
    """Gmail looks configured (OAuth client + token files exist); sending is replaced by a recorder."""
    folder = tmp_path / "gmail"
    folder.mkdir()
    for name in ("gcp-oauth.keys.json", "credentials.json"):
        (folder / name).write_text("{}", encoding="utf-8")
    monkeypatch.setenv("GMAIL_OAUTH_PATH", str(folder / "gcp-oauth.keys.json"))
    monkeypatch.setenv("GMAIL_CREDENTIALS_PATH", str(folder / "credentials.json"))
    monkeypatch.setenv("EMAIL_RETRY_SECONDS", "0")
    state = SimpleNamespace(calls=[], replies=[], folder=folder)

    def fake_send(to, subject, body, html_body=None):
        state.calls.append({"to": to, "subject": subject, "body": body, "html": html_body})
        return state.replies.pop(0) if state.replies else {"ok": True, "message_id": f"msg-{len(state.calls)}"}

    monkeypatch.setattr(mcp_client, "call_gmail_send", fake_send)
    return state


def _screened_application(app, client):
    job_id = open_python_job(client)
    register(client, "dana@x.test", "candidate", "Dana Levi")
    cv = Path("samples/cv_python.txt")
    client.post(
        f"/applications/apply/{job_id}",
        data={"cv": (BytesIO(cv.read_bytes()), cv.name)},
        follow_redirects=True,
    )
    logout(client)
    with app.app_context():
        application_id = list_for_job(job_id)[0]["id"]
        start_screening(application_id)
        complete_screening(application_id, REPORT)
    login(client, "hr@x.test")
    return application_id


def _decide(client, application_id, decision, reason):
    return client.post(
        f"/applications/{application_id}/decide",
        data={"decision": decision, "reason": reason},
        follow_redirects=True,
    )


def _events(application_id, *types):
    return [e for e in EventStore.for_aggregate(application_id) if e["event_type"] in types]


def test_decision_view_only_records_the_decision(app, client, gmail):
    application_id = _screened_application(app, client)
    page = _decide(client, application_id, "interview", "Strong Flask background").get_data(as_text=True)

    assert gmail.calls == []
    assert "בתהליך הרקע" in page and "ממתין לשליחה" in page
    with app.app_context():
        assert _events(application_id, "DecisionEmailSent", "DecisionEmailFailed") == []
        decision = _events(application_id, "InterviewScheduled")[0]
        [pending] = pending_decision_emails()
    assert pending["decision_event_id"] == decision["event_id"]
    assert pending["candidate_email"] == "dana@x.test"
    assert pending["job_title"] == "Python Backend"
    assert pending["reason"] == "Strong Flask background"


def test_worker_sends_each_decision_once_and_records_it(app, client, gmail):
    application_id = _screened_application(app, client)
    _decide(client, application_id, "interview", "Strong Flask background")

    with app.app_context():
        assert send_pending_emails() == 1
        assert send_pending_emails() == 0
        decision = _events(application_id, "InterviewScheduled")[0]
        [sent] = _events(application_id, "DecisionEmailSent")
        assert pending_decision_emails() == []
        with pytest.raises(ValueError):
            record_email_sent(application_id, decision["event_id"], "dana@x.test", "again", "msg-x")

    assert len(gmail.calls) == 1
    call = gmail.calls[0]
    assert call["to"] == "dana@x.test"
    assert "Python Backend" in call["subject"] and "ראיון" in call["subject"]
    assert "Dana Levi" in call["body"] and "Strong Flask background" in call["body"]
    assert 'dir="rtl"' in call["html"]
    assert sent["payload"]["decision_event_id"] == decision["event_id"]
    assert sent["payload"]["message_id"] == "msg-1"
    assert sent["metadata"]["source"] == "gmail-mcp"
    page = client.get(f"/applications/{application_id}").get_data(as_text=True)
    assert "מייל נשלח ל-dana@x.test" in page

    _decide(client, application_id, "offer", "Great interview")
    with app.app_context():
        assert send_pending_emails() == 1
        assert len(_events(application_id, "DecisionEmailSent")) == 2
    assert "הצעת עבודה" in gmail.calls[1]["subject"]


def test_failed_send_is_recorded_retried_and_capped(app, client, gmail, monkeypatch):
    application_id = _screened_application(app, client)
    _decide(client, application_id, "reject", "Missing SQL experience")
    gmail.replies.extend([{"ok": False, "error": "Error: invalid_grant"}] * 3)

    with app.app_context():
        assert send_pending_emails() == 0
        monkeypatch.setenv("EMAIL_RETRY_SECONDS", "3600")
        send_pending_emails()
        assert len(gmail.calls) == 1
        monkeypatch.setenv("EMAIL_RETRY_SECONDS", "0")
        send_pending_emails()
        send_pending_emails()
        send_pending_emails()
        failures = _events(application_id, "DecisionEmailFailed")
        assert pending_decision_emails() == []

    assert len(gmail.calls) == 3
    assert [f["payload"]["attempt"] for f in failures] == [1, 2, 3]
    assert [f["payload"]["final"] for f in failures] == [False, False, True]
    assert failures[0]["payload"]["error"] == "Error: invalid_grant"
    page = client.get(f"/applications/{application_id}").get_data(as_text=True)
    assert "שליחת המייל נכשלה" in page and "invalid_grant" in page


def test_without_gmail_login_nothing_is_sent_or_recorded(app, client, gmail):
    (gmail.folder / "credentials.json").unlink()
    application_id = _screened_application(app, client)
    _decide(client, application_id, "interview", "Strong Flask background")

    with app.app_context():
        assert send_pending_emails() == 0
        assert _events(application_id, "DecisionEmailSent", "DecisionEmailFailed") == []
        assert len(pending_decision_emails()) == 1
    assert gmail.calls == []


def test_email_written_before_gmail_worker_closes_the_decision(app, client, gmail):
    application_id = _screened_application(app, client)
    _decide(client, application_id, "interview", "Strong Flask background")
    with app.app_context():
        EventStore.append(
            "DecisionEmailSent",
            "Application",
            application_id,
            {"to": "dana@x.test", "subject": "old stub"},
            {"source": "gmail-mcp"},
        )
        assert send_pending_emails() == 0
    assert gmail.calls == []
    assert "המייל לא נשלח בפועל" in client.get(f"/applications/{application_id}").get_data(as_text=True)


def test_compose_email_is_deterministic_hebrew():
    item = {"decision": "reject", "job_title": "Python Backend", "candidate_name": "Dana", "reason": "<b>SQL</b>"}
    subject, text, html_body = compose_email(item)
    assert subject == "עדכון לגבי מועמדותך למשרת Python Backend"
    assert text.startswith("שלום Dana,") and "דברי צוות הגיוס: <b>SQL</b>" in text
    assert "&lt;b&gt;SQL&lt;/b&gt;" in html_body
    assert compose_email(item) == (subject, text, html_body)


def test_gmail_mcp_contract(monkeypatch):
    seen = {}

    def fake_stdio(**kwargs):
        seen.update(kwargs)
        return {"text": "Email sent successfully with ID: 18f3abc"}

    monkeypatch.setattr(mcp_client, "_stdio_call", fake_stdio)
    result = mcp_client.call_gmail_send("dana@x.test", "נושא", "גוף", "<p>גוף</p>")
    assert result == {"ok": True, "message_id": "18f3abc"}
    assert "send_email" in seen["tool_name"]
    assert seen["arguments"]["to"] == ["dana@x.test"]
    assert seen["arguments"]["mimeType"] == "multipart/alternative"

    monkeypatch.setattr(mcp_client, "_stdio_call", lambda **kwargs: {"text": "Error: Invalid Credentials"})
    assert mcp_client.call_gmail_send("dana@x.test", "s", "b") == {"ok": False, "error": "Error: Invalid Credentials"}
