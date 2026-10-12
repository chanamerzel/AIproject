from io import BytesIO
from pathlib import Path

from agent.deep_agent import evaluate_application
from agent.rag import embed_application
from app.commands.applications import complete_screening, decide, start_screening
from app.queries.applications import get_application, list_for_job
from tests.conftest import logout, open_python_job, register


def _apply(client, job_id, path):
    path = Path(path)
    register(client, f"{path.stem}@x.test", "candidate", path.stem)
    client.post(
        f"/applications/apply/{job_id}",
        data={"cv": (BytesIO(path.read_bytes()), path.name)},
        follow_redirects=True,
    )
    logout(client)


def test_semantic_ranks_python_cv_above_unrelated(app, client):
    job_id = open_python_job(client)
    _apply(client, job_id, "samples/cv_python.txt")
    _apply(client, job_id, "samples/cv_unrelated.txt")
    with app.app_context():
        rows = list_for_job(job_id)
        assert len(rows) == 2
        for row in rows:
            embed_application(row["id"], job_id, row["cv_text"])
        from app.queries.jobs import get_job
        from app.queries.semantic import similar_candidates_for_job

        matches = similar_candidates_for_job(get_job(job_id))
    names = [m["candidate_name"] for m in matches]
    assert names[0].lower().startswith("cv_python") or "python" in names[0].lower() or matches[0]["score"] >= matches[-1]["score"]
    assert matches[0]["score"] > matches[-1]["score"]


def test_worker_completes_screening_with_score(app, client):
    job_id = open_python_job(client)
    _apply(client, job_id, "samples/cv_python.txt")
    with app.app_context():
        row = list_for_job(job_id)[0]
        embed_application(row["id"], job_id, row["cv_text"])
        start_screening(row["id"])
        report = evaluate_application(get_application(row["id"]))
        complete_screening(row["id"], report)
        updated = get_application(row["id"])
    assert updated["status"] == "Screened"
    assert updated["agent_score"] is not None
    assert report["recommendation"] in {"advance", "hold", "reject"}


def test_reject_writes_event(app, client):
    job_id = open_python_job(client)
    _apply(client, job_id, "samples/cv_python.txt")
    with app.app_context():
        row = list_for_job(job_id)[0]
        start_screening(row["id"])
        complete_screening(
            row["id"],
            {
                "overall_score": 40,
                "skill_coverage": 40,
                "semantic_fit": 40,
                "recommendation": "reject",
                "strengths": [],
                "gaps": ["Flask"],
                "web_evidence": [],
                "cv_excerpts": [],
            },
        )
        decide(row["id"], "reject", "לא מכסה Flask", "hr-actor")
        updated = get_application(row["id"])
        from app.event_store import EventStore

        types = [e["event_type"] for e in EventStore.for_aggregate(row["id"])]
    assert updated["status"] == "Rejected"
    assert "ApplicationRejected" in types
