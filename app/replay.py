"""Rebuild projection tables from the event store. Proof of Event Sourcing."""

from app import db
from app.projections import apply_event


def all_events() -> list[dict]:
    return db.fetch_all(
        """SELECT * FROM events
           ORDER BY occurred_at ASC, version ASC"""
    )


def rebuild_read_models() -> int:
    db.execute("DELETE FROM applications")
    db.execute("DELETE FROM jobs")
    db.execute("DELETE FROM users")
    events = all_events()
    for event in events:
        apply_event(event)
    return len(events)


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        n = rebuild_read_models()
        print(f"replayed {n} events")
