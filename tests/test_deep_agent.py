"""F7: the deepagents loop calls the tools and its report is reconciled with tool output."""

import json
from io import BytesIO
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from agent import deep_agent
from agent.rag import embed_application
from app.queries.applications import get_application, list_for_job
from tests.conftest import logout, open_python_job, register


class ScriptedToolModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def _call(name, args, i):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{i}"}])


def _submitted_application(app, client):
    job_id = open_python_job(client)
    cv = Path("samples/cv_python.txt")
    register(client, "dana@x.test", "candidate", "Dana")
    client.post(
        f"/applications/apply/{job_id}",
        data={"cv": (BytesIO(cv.read_bytes()), cv.name)},
        follow_redirects=True,
    )
    logout(client)
    with app.app_context():
        row = list_for_job(job_id)[0]
        embed_application(row["id"], job_id, row["cv_text"])
        return get_application(row["id"])


def test_deep_agent_runs_tools_and_reconciles_report(app, client, monkeypatch):
    application = _submitted_application(app, client)
    cv_text = application["cv_text"]
    final = {
        "overall_score": 99,
        "skill_coverage": 99,
        "semantic_fit": 99,
        "web_score": 50,
        "recommendation": "advance",
        "summary": "Strong Python and Flask background.",
        "strengths": ["Python", "Flask"],
        "gaps": [],
        "web_evidence": [],
        "cv_excerpts": [],
    }
    script = iter(
        [
            _call("extract_resume_profile", {"cv_text": cv_text}, 1),
            _call(
                "evaluate_requirement_coverage",
                {"must_have_skills": application["must_have_skills"], "cv_text": cv_text},
                2,
            ),
            _call("rag_cv_against_job", {}, 3),
            _call("tavily_web_search", {"query": "Flask framework"}, 4),
            AIMessage(content=json.dumps(final)),
        ]
    )
    monkeypatch.setenv("FITSCREEN_AGENT_MODE", "deepagent")
    monkeypatch.setattr(deep_agent, "_build_model", lambda: ScriptedToolModel(messages=script))

    with app.app_context():
        report = deep_agent.evaluate_application(application)

    assert report["runtime"].startswith("deepagents")
    assert report["tools_skipped_by_agent"] == []
    assert set(report["tools_used"]) == set(deep_agent.REQUIRED_TOOLS)
    assert report["summary"] == final["summary"]
    # The model claimed 99 everywhere; the stored scores come from the tools instead.
    assert report["skill_coverage"] != 99
    assert 0 <= report["overall_score"] <= 100
    assert report["recommendation"] in {"advance", "hold", "reject"}


def test_worker_refuses_without_llm(monkeypatch):
    monkeypatch.setenv("FITSCREEN_AGENT_MODE", "deepagent")
    monkeypatch.setenv("LLM_PROVIDER", "")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    from agent.worker import _preflight

    assert "No LLM configured" in _preflight()
    with pytest.raises(deep_agent.AgentNotConfigured):
        deep_agent._build_model()


def test_health_reports_database_backend(client):
    body = client.get("/health").get_json()
    assert body["status"] == "ok"
    assert body["database"]["backend"] == "sqlite"
    assert body["embeddings"]["model"] == "token-hash"
    assert set(body["database"]["counts"]) == {"events", "users", "jobs", "applications"}
