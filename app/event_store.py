import json
import uuid
from datetime import datetime, timezone

from app import db


class EventStore:
    @staticmethod
    def next_version(aggregate_id: str) -> int:
        row = db.fetch_one(
            "SELECT MAX(version) AS v FROM events WHERE aggregate_id = ?",
            (aggregate_id,),
        )
        current = row["v"] if row and row["v"] is not None else 0
        return int(current) + 1

    @staticmethod
    def append(
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: dict,
        metadata: dict | None = None,
    ) -> dict:
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "version": EventStore.next_version(aggregate_id),
            "payload_json": json.dumps(payload, ensure_ascii=False),
            "metadata_json": json.dumps(metadata or {}, ensure_ascii=False),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        db.execute(
            """INSERT INTO events (event_id, event_type, aggregate_type, aggregate_id,
               version, payload_json, metadata_json, occurred_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event["event_id"],
                event["event_type"],
                event["aggregate_type"],
                event["aggregate_id"],
                event["version"],
                event["payload_json"],
                event["metadata_json"],
                event["occurred_at"],
            ),
        )
        from app.projections import apply_event

        apply_event(event)
        return event

    @staticmethod
    def for_aggregate(aggregate_id: str) -> list[dict]:
        rows = db.fetch_all(
            "SELECT * FROM events WHERE aggregate_id = ? ORDER BY version ASC",
            (aggregate_id,),
        )
        for row in rows:
            row["payload"] = json.loads(row["payload_json"])
            row["metadata"] = json.loads(row["metadata_json"])
        return rows
