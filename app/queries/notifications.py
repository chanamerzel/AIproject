"""Decision emails, read from the event stream: what happened to the email of each HR decision."""

import json

from app import db
from app.queries.applications import contacts_by_application

DECISION_EVENTS = {
    "InterviewScheduled": "interview",
    "ApplicationRejected": "reject",
    "OfferExtended": "offer",
    "JobClosureAnnounced": "closed",
}
OUTCOME_EVENTS = ("DecisionEmailSent", "DecisionEmailFailed")
# "failed" is a non-final failure: the worker tries again.
OPEN_STATUSES = ("pending", "failed")


def _email_states(events: list[dict]) -> list[dict]:
    """One entry per decision event, in stream order, with the outcome of its email."""
    states, by_decision = [], {}
    for event in events:
        etype, payload = event["event_type"], event["payload"]
        if etype in DECISION_EVENTS:
            state = {
                "application_id": event["aggregate_id"],
                "decision_event_id": event["event_id"],
                "decision": DECISION_EVENTS[etype],
                "reason": payload.get("reason") or "",
                "decided_at": event["occurred_at"],
                "status": "pending",
                "attempts": 0,
                "to": None,
                "subject": None,
                "error": None,
                "last_failed_at": None,
            }
            states.append(state)
            by_decision[event["event_id"]] = state
        elif etype in OUTCOME_EVENTS:
            state = by_decision.get(payload.get("decision_event_id"))
            if state is None:
                # Written before the Gmail worker existed: nothing was sent, but the decision is closed.
                if etype == "DecisionEmailSent":
                    previous = [s for s in states if s["application_id"] == event["aggregate_id"]]
                    if previous:
                        previous[-1].update(status="legacy", to=payload.get("to"), subject=payload.get("subject"))
                continue
            state["to"] = payload.get("to")
            if etype == "DecisionEmailSent":
                state.update(status="sent", subject=payload.get("subject"), error=None)
            else:
                state["attempts"] += 1
                state.update(
                    status="failed_final" if payload.get("final") else "failed",
                    error=payload.get("error"),
                    last_failed_at=event["occurred_at"],
                )
    return states


def decision_emails(application_id: str, events: list[dict]) -> list[dict]:
    """Email state for one application. The caller passes that application's event stream."""
    owned = [event for event in events if event.get("aggregate_id", application_id) == application_id]
    return _email_states(owned)


def pending_decision_emails() -> list[dict]:
    """Decisions whose email was neither sent nor given up on, with the recipient and job details."""
    types = (*DECISION_EVENTS, *OUTCOME_EVENTS)
    rows = db.fetch_all(
        f"""SELECT * FROM events WHERE event_type IN ({", ".join("?" for _ in types)})
            ORDER BY aggregate_id, version""",
        types,
    )
    for row in rows:
        row["payload"] = json.loads(row["payload_json"])
    open_states = [state for state in _email_states(rows) if state["status"] in OPEN_STATUSES]
    contacts = contacts_by_application([state["application_id"] for state in open_states])
    pending = []
    for state in open_states:
        contact = contacts.get(state["application_id"])
        if not contact:
            continue
        state.update(
            candidate_email=contact["candidate_email"],
            candidate_name=contact["candidate_name"],
            job_title=contact["job_title"],
        )
        pending.append(state)
    return sorted(pending, key=lambda s: s["decided_at"])
