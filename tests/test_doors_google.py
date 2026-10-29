"""F1: two sign-in doors and Google sign-in. Google itself is replaced; no network calls."""

import pytest

from app import create_app, google_auth
from app.db import fetch_one
from tests.conftest import TEST_DATABASE_URL, logout, register


def test_staff_register_needs_role_and_lands_on_dashboard(client):
    missing = client.post(
        "/auth/recruit/register",
        data={"email": "noa@x.test", "password": "secret1", "full_name": "Noa"},
        follow_redirects=True,
    )
    assert "יש לבחור תפקיד" in missing.get_data(as_text=True)

    done = client.post(
        "/auth/recruit/register",
        data={"email": "noa@x.test", "password": "secret1", "full_name": "Noa", "role": "hiring_manager"},
        follow_redirects=True,
    )
    assert done.request.path == "/dashboard/"
    with client.application.app_context():
        assert fetch_one("SELECT role FROM users WHERE email = ?", ("noa@x.test",))["role"] == "hiring_manager"


def test_candidate_register_ignores_a_forged_role(client):
    client.post(
        "/auth/register",
        data={"email": "c@x.test", "password": "secret1", "full_name": "C", "role": "hr"},
    )
    with client.application.app_context():
        assert fetch_one("SELECT role FROM users WHERE email = ?", ("c@x.test",))["role"] == "candidate"


def test_each_door_turns_away_the_other_kind_of_account(client):
    register(client, "c@x.test", "candidate")
    logout(client)
    wrong = client.post("/auth/recruit/login", data={"email": "c@x.test", "password": "secret1"})
    assert "דלת המועמדים" in wrong.get_data(as_text=True)
    assert client.get("/dashboard/").status_code == 302

    register(client, "hr@x.test", "hr")
    logout(client)
    wrong = client.post("/auth/login", data={"email": "hr@x.test", "password": "secret1"})
    assert "דלת המגייסים" in wrong.get_data(as_text=True)


@pytest.fixture()
def google_app(tmp_path, monkeypatch):
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "DATABASE_URL": TEST_DATABASE_URL or f"sqlite:///{tmp_path / 'g.db'}",
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "CHROMA_PATH": str(tmp_path / "chroma"),
            "GOOGLE_CLIENT_ID": "client-id",
            "GOOGLE_CLIENT_SECRET": "client-secret",
        }
    )
    if TEST_DATABASE_URL:
        from app import db

        for table in ("events", "applications", "jobs", "users"):
            db.execute(f"DELETE FROM {table}")
    identity = {"email": "dana@gmail.test", "name": "Dana Levi", "email_verified": True}
    monkeypatch.setattr(google_auth, "start_login", lambda redirect_uri: ("redirect " + redirect_uri, 302))
    monkeypatch.setattr(google_auth, "finish_login", lambda: dict(identity))
    application.google_identity = identity
    return application


def test_google_button_hidden_without_keys(client):
    assert "Google" not in client.get("/auth/login").get_data(as_text=True)
    assert client.get("/auth/google").status_code == 404


def test_google_candidate_first_sign_in_registers_with_event(google_app):
    client = google_app.test_client()
    assert "כניסה עם Google" in client.get("/auth/login").get_data(as_text=True)
    start = client.get("/auth/google?door=candidate")
    assert start.status_code == 302 and "/auth/google/callback" in start.get_data(as_text=True)
    page = client.get("/auth/google/callback", follow_redirects=True)
    assert page.request.path == "/jobs/"
    with google_app.app_context():
        user = fetch_one("SELECT role, auth_provider, full_name FROM users WHERE email = ?", ("dana@gmail.test",))
        event = fetch_one("SELECT payload_json FROM events WHERE event_type = ?", ("UserRegistered",))
    assert user == {"role": "candidate", "auth_provider": "google", "full_name": "Dana Levi"}
    assert '"auth_provider": "google"' in event["payload_json"]

    logout(client)
    blocked = client.post("/auth/login", data={"email": "dana@gmail.test", "password": "secret1"})
    assert "שגויים" in blocked.get_data(as_text=True)


def test_google_staff_role_comes_from_our_door(google_app):
    client = google_app.test_client()
    client.get("/auth/google?door=staff&role=hiring_manager")
    page = client.get("/auth/google/callback", follow_redirects=True)
    assert page.request.path == "/dashboard/"
    with google_app.app_context():
        assert fetch_one("SELECT role FROM users WHERE email = ?", ("dana@gmail.test",))["role"] == "hiring_manager"


def test_google_staff_without_role_is_sent_back(google_app):
    client = google_app.test_client()
    client.get("/auth/google?door=staff&role=admin")
    page = client.get("/auth/google/callback", follow_redirects=True)
    assert "יש לבחור תפקיד" in page.get_data(as_text=True)


def test_google_signs_in_existing_account_but_keeps_doors(google_app):
    client = google_app.test_client()
    register(client, "dana@gmail.test", "candidate", "Dana")
    logout(client)
    client.get("/auth/google?door=staff&role=hr")
    page = client.get("/auth/google/callback", follow_redirects=True)
    assert "דלת המועמדים" in page.get_data(as_text=True)

    client.get("/auth/google?door=candidate")
    page = client.get("/auth/google/callback", follow_redirects=True)
    assert page.request.path == "/jobs/"
    with google_app.app_context():
        assert fetch_one("SELECT COUNT(*) AS n FROM users WHERE email = ?", ("dana@gmail.test",))["n"] == 1


def test_google_unverified_email_is_refused(google_app):
    google_app.google_identity["email_verified"] = False
    client = google_app.test_client()
    client.get("/auth/google?door=candidate")
    page = client.get("/auth/google/callback", follow_redirects=True)
    assert "לא אישר" in page.get_data(as_text=True)
