from tests.conftest import logout, register


def test_register_writes_user_registered_event(app, client):
    response = register(client, "a@x.test", "candidate", "Ada")
    assert response.status_code == 200
    from app.db import fetch_one

    with app.app_context():
        row = fetch_one("SELECT event_type FROM events WHERE event_type = ?", ("UserRegistered",))
    assert row is not None


def test_login_rejects_bad_password(client):
    register(client, "a@x.test", "candidate")
    logout(client)
    response = client.post(
        "/auth/login",
        data={"email": "a@x.test", "password": "wrong-password"},
        follow_redirects=True,
    )
    assert "שגויים" in response.get_data(as_text=True)


def test_candidate_cannot_open_hr_dashboard(client):
    register(client, "a@x.test", "candidate")
    response = client.get("/dashboard/")
    assert response.status_code == 403
