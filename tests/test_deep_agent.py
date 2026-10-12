"""F7: the deepagents loop calls the tools and its report is reconciled with tool output."""

import json
import os
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


def test_deep_agent_delegates_to_subagents_and_reconciles_report(app, client, monkeypatch):
    application = _submitted_application(app, client)
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
    # One scripted model serves the orchestrator and both subagents, in call order.
    script = iter(
        [
            _call("task", {"subagent_type": "cv-analyst", "description": "Analyse the CV"}, 1),
            _call("extract_resume_profile", {}, 2),
            _call("evaluate_requirement_coverage", {}, 3),
            _call("rag_cv_against_job", {}, 4),
            AIMessage(content="Python and Flask matched, coverage reported by the tool."),
            _call("task", {"subagent_type": "web-researcher", "description": "Verify Flask"}, 5),
            _call("tavily_web_search", {"query": "Flask framework"}, 6),
            AIMessage(content="Web evidence inconclusive."),
            AIMessage(content=json.dumps(final)),
        ]
    )
    monkeypatch.setenv("FITSCREEN_AGENT_MODE", "deepagent")
    monkeypatch.setattr(deep_agent, "model_chain", lambda: [("scripted", ScriptedToolModel(messages=script))])

    with app.app_context():
        report = deep_agent.evaluate_application(application)

    assert report["runtime"].startswith("deepagents:scripted")
    assert report["agent_report_valid"] is True
    assert report["tools_skipped_by_agent"] == []
    assert set(report["tools_used"]) == set(deep_agent.REQUIRED_TOOLS)
    assert {c["by"] for c in report["delegation"]} == {"cv-analyst", "web-researcher"}
    assert report["summary"] == final["summary"]
    # The model claimed 99 everywhere; the stored scores come from the tools instead.
    assert report["skill_coverage"] != 99
    assert 0 <= report["overall_score"] <= 100
    assert report["recommendation"] in {"advance", "hold", "reject"}


def test_worker_refuses_without_llm(monkeypatch):
    monkeypatch.setenv("FITSCREEN_AGENT_MODE", "deepagent")
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    from agent.worker import _preflight

    reason = _preflight()
    assert "No LLM configured" in reason
    assert "ollama" in reason and "gemini" in reason
    with pytest.raises(deep_agent.AgentNotConfigured):
        deep_agent.model_chain()


def test_auto_prefers_each_gemini_model_then_ollama(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-a, gemini-b")
    monkeypatch.setattr(deep_agent, "ollama_status", lambda: None)
    chain = deep_agent.model_chain()
    assert [name for name, _ in chain] == ["gemini", "gemini", "ollama"]
    assert [model.model for _, model in chain[:2]] == ["gemini-a", "gemini-b"]


def test_auto_uses_ollama_when_gemini_has_no_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "auto")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setattr(deep_agent, "ollama_status", lambda: None)
    assert [name for name, _ in deep_agent.model_chain()] == ["ollama"]


TAVILY_TEXT = """Detailed Results:

Title: Flask (web framework) - Wikipedia
ID: 624645-00
URL: https://en.wikipedia.org/wiki/Flask_(web_framework)
Content: Flask is a micro web framework written in Python.
It has no database abstraction layer.

Title: Welcome to Flask
URL: https://flask.palletsprojects.com/
Content: Flask is a lightweight WSGI web application framework."""


def test_tavily_text_response_is_parsed_into_sources():
    from agent.mcp_client import _as_results

    results = _as_results({"text": TAVILY_TEXT})
    assert [r["url"] for r in results] == [
        "https://en.wikipedia.org/wiki/Flask_(web_framework)",
        "https://flask.palletsprojects.com/",
    ]
    assert results[0]["title"] == "Flask (web framework) - Wikipedia"
    assert "no database abstraction layer" in results[0]["content"]


def test_report_drops_web_evidence_with_invented_urls():
    from agent.mcp_client import _as_results

    application = {"id": "a1", "job_id": "j1", "cv_text": "", "must_have_skills": "Python"}
    trace = {
        "extract_resume_profile": {},
        "evaluate_requirement_coverage": {"coverage_score": 50, "must_have_matched": ["Python"], "must_have_missing": []},
        "rag_cv_against_job": {"semantic_fit_percent": 40},
        "tavily_web_search": [{"query": "flask", "ok": True, "results": _as_results({"text": TAVILY_TEXT})}],
    }
    report = {"web_evidence": [{"title": "Made up", "url": "https://invented.example", "finding": "x"}]}
    result = deep_agent._finalize(report, trace, application, runtime="test")
    assert {e["url"] for e in result["web_evidence"]} == {
        "https://en.wikipedia.org/wiki/Flask_(web_framework)",
        "https://flask.palletsprojects.com/",
    }
    assert result["summary"].startswith("Covers 1 of 1 must-have skills")


def test_health_reports_database_backend(client):
    body = client.get("/health").get_json()
    assert body["status"] == "ok"
    expected = "mssql" if os.getenv("TEST_DATABASE_URL") else "sqlite"
    assert body["database"]["backend"] == expected
    assert body["embeddings"]["model"] == "token-hash"
    assert set(body["database"]["counts"]) == {"events", "users", "jobs", "applications"}
