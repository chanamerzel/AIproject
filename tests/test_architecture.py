from pathlib import Path

FORBIDDEN = ("טיסה", "טיסות", "כרטיס טיסה", "flight", "airline")


def test_command_writes_event_before_projection(app, client):
    client.post(
        "/auth/register",
        data={
            "email": "a@x.test",
            "password": "secret1",
            "full_name": "Ada",
            "role": "candidate",
        },
        follow_redirects=True,
    )
    from app.db import fetch_one

    with app.app_context():
        event = fetch_one("SELECT * FROM events WHERE event_type = ?", ("UserRegistered",))
        user = fetch_one("SELECT * FROM users WHERE email = ?", ("a@x.test",))
    assert event is not None
    assert user is not None
    assert event["aggregate_id"] == user["id"]


def test_queries_never_append_events():
    root = Path("app/queries")
    for path in root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "EventStore.append" not in text
        assert "event_store.append" not in text


def test_product_code_has_no_flight_domain():
    for path in Path("app").rglob("*"):
        if path.suffix.lower() not in {".py", ".html"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for word in FORBIDDEN:
            assert word not in text, f"{word} found in {path}"
