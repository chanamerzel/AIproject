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
    report = {
        "web_score": 99,
        "web_evidence": [{"title": "Made up", "url": "https://invented.example", "finding": "x"}],
    }
    result = deep_agent._finalize(report, trace, application, runtime="test")
    assert result["web_evidence"] == []
    assert result["web_score"] == 0
    assert "השם המלא" in result["web_note"]
    assert result["summary"].startswith("קורות החיים מכסים 1 מתוך 1 כישורי חובה")
    assert result["agent_state"]["step_count"] == 4
    assert result["agent_state"]["current_step"] == 4


def test_web_search_uses_quoted_name_not_github_url_or_generic_skills():
    queries = deep_agent._web_queries(
        {
            "github_url": "https://github.com/smerzel",
            "linkedin_url": "https://www.linkedin.com/in/sara-merzel-91b72436b",
            "last_company": "NovaLabs",
        },
        {"candidate_name": "Sara Merzel", "job_title": "Python Backend", "must_have_skills": "Python, Flask"},
    )
    assert queries == ['"Sara Merzel"', '"Sara Merzel" NovaLabs', '"Sara Merzel" Python Backend']
    assert all("linkedin" not in q.casefold() for q in queries)
    assert all("github.com" not in q.casefold() for q in queries)
    assert all(q != "Python" and "software engineering" not in q for q in queries)


def test_web_page_about_the_candidate_is_kept():
    application = {"candidate_name": "Sara Merzel", "cv_text": "", "must_have_skills": "Python"}
    trace = {
        "extract_resume_profile": {"github_login": "smerzel"},
        "evaluate_requirement_coverage": {
            "coverage_score": 50,
            "must_have_matched": ["Python"],
            "must_have_missing": ["Flask"],
            "skill_evidence": [
                {"skill": "Python", "matched": True, "quote": "Python on the backend"},
                {"skill": "Flask", "matched": False, "quote": None},
            ],
        },
        "rag_cv_against_job": {"semantic_fit_percent": 40},
        "tavily_web_search": [
            {
                "query": "sara",
                "ok": True,
                "results": [
                    {"title": "Flask", "url": "https://flask.palletsprojects.com/", "content": "framework"},
                    {"title": "Sara Merzel", "url": "https://github.com/smerzel", "content": "profile"},
                ],
            }
        ],
    }
    result = deep_agent._finalize({}, trace, application, runtime="test")
    assert [item["url"] for item in result["web_evidence"]] == ["https://github.com/smerzel"]
    assert result["github_status"] == "unchecked"
    assert result["web_score"] >= 35
    assert not result["web_note"]
    labels = [item["label"] for item in result["agent_state"]["citations"]]
    assert labels == ["Python", "Flask"]


def test_saved_report_without_agent_state_still_shows_plan_and_quote():
    report = {
        "overall_score": 83,
        "skill_coverage": 100,
        "web_score": 60,
        "cv_excerpts": ["Built Python services."],
        "web_evidence": [{"title": "Flask", "url": "https://flask.palletsprojects.com/", "finding": "framework"}],
        "tools_used": [
            "extract_resume_profile",
            "evaluate_requirement_coverage",
            "rag_cv_against_job",
            "tavily_web_search",
        ],
    }
    shown = deep_agent.state_for_saved_report(
        report, "Five years of Python on the backend.", "Python", candidate_name="Dana Candidate"
    )
    assert shown["agent_state"]["current_step"] == 4
    quotes = [c["quote"] for c in shown["agent_state"]["citations"] if c["kind"] == "skill" and c.get("quote")]
    assert quotes and "Python" in quotes[0]
    assert shown["web_evidence"] == []
    assert shown["web_score"] == 60
    assert shown["overall_score"] == 83
    assert report.get("agent_state") is None


def test_github_lookup_reads_public_api(monkeypatch):
    monkeypatch.delenv("FITSCREEN_FAKE_EMBEDDINGS", raising=False)

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "login": "smerzel",
                "html_url": "https://github.com/smerzel",
                "name": "Sara",
                "bio": "dev",
                "public_repos": 2,
            }

    monkeypatch.setattr("agent.github_public.httpx.get", lambda *args, **kwargs: FakeResponse())
    from agent.github_public import lookup

    found = lookup("smerzel")
    assert found["ok"] is True
    assert found["html_url"] == "https://github.com/smerzel"


def test_github_inspect_collects_repo_languages(monkeypatch):
    monkeypatch.delenv("FITSCREEN_FAKE_EMBEDDINGS", raising=False)

    class FakeResponse:
        def __init__(self, payload):
            self.status_code = 200
            self._payload = payload

        def json(self):
            return self._payload

    def fake_get(url, **kwargs):
        if url.endswith("/repos"):
            return FakeResponse(
                [
                    {
                        "name": "services",
                        "html_url": "https://github.com/smerzel/services",
                        "language": "Python",
                        "description": "API",
                        "pushed_at": "2026-02-01T00:00:00Z",
                        "fork": False,
                    }
                ]
            )
        return FakeResponse(
            {
                "login": "smerzel",
                "html_url": "https://github.com/smerzel",
                "name": "Sara",
                "bio": "",
                "public_repos": 1,
            }
        )

    monkeypatch.setattr("agent.github_public.httpx.get", fake_get)
    from agent.github_public import inspect

    found = inspect("smerzel")
    assert found["ok"] is True
    assert found["languages"] == ["Python"]
    assert found["repos"][0]["name"] == "services"


def test_github_portfolio_is_separate_from_tavily_junk(monkeypatch):
    monkeypatch.setattr(
        "agent.github_public.inspect",
        lambda login: {
            "ok": True,
            "login": login,
            "html_url": f"https://github.com/{login}",
            "name": "Sara Merzel",
            "bio": "",
            "public_repos": 4,
            "languages": ["Python"],
            "last_activity": "2026-01-01",
            "repos": [
                {
                    "name": "services",
                    "html_url": f"https://github.com/{login}/services",
                    "language": "Python",
                    "description": "backend",
                    "pushed_at": "2026-01-01",
                }
            ],
        },
    )
    application = {"candidate_name": "Sara Merzel", "cv_text": "", "must_have_skills": "Python"}
    trace = {
        "extract_resume_profile": {
            "github_login": "smerzel",
            "github_url": "https://github.com/smerzel",
        },
        "evaluate_requirement_coverage": {
            "coverage_score": 50,
            "must_have_matched": ["Python"],
            "must_have_missing": [],
        },
        "rag_cv_against_job": {"semantic_fit_percent": 40},
        "tavily_web_search": [
            {
                "query": "python",
                "ok": True,
                "results": [{"title": "Flask", "url": "https://flask.palletsprojects.com/", "content": "framework"}],
            }
        ],
    }
    result = deep_agent._finalize({}, trace, application, runtime="test")
    assert result["github_status"] == "verified"
    assert result["web_evidence"] == []
    assert "השם המלא" in result["web_note"]
    assert result["github_portfolio"]["matched_skills"] == ["Python"]
    assert result["github_portfolio"]["repos"][0]["name"] == "services"
    assert result["web_score"] == 35


def test_github_api_404_marks_account_missing(monkeypatch):
    monkeypatch.setattr("agent.github_public.inspect", lambda login: {"ok": False, "login": login})
    application = {"candidate_name": "Sara Merzel", "must_have_skills": "Python"}
    trace = {
        "extract_resume_profile": {"github_login": "no-such-user-xyz", "github_url": "https://github.com/no-such-user-xyz"},
        "evaluate_requirement_coverage": {"coverage_score": 50, "must_have_matched": ["Python"], "must_have_missing": []},
        "rag_cv_against_job": {"semantic_fit_percent": 40},
        "tavily_web_search": [
            {"query": "python", "ok": True, "results": [{"title": "Flask", "url": "https://flask.palletsprojects.com/", "content": "framework"}]}
        ],
    }
    result = deep_agent._finalize({}, trace, application, runtime="test")
    assert result["github_status"] == "not_found"
    assert result["web_score"] == 0


def test_saved_report_shows_github_from_cv_without_changing_score():
    report = {
        "overall_score": 83,
        "skill_coverage": 100,
        "web_score": 0,
        "github_status": "not_provided",
        "web_evidence": [{"title": "Flask", "url": "https://flask.palletsprojects.com/"}],
        "web_note": "לא נמצא ברשת פרופיל של המועמד.",
    }
    shown = deep_agent.state_for_saved_report(
        report,
        "Sara Merzel\nGitHub: https://github.com/smerzel",
        "Python",
        candidate_name="Sara Merzel",
    )
    assert shown["overall_score"] == 83
    assert shown["web_score"] == 0
    assert shown["profile"]["github_url"] == "https://github.com/smerzel"
    assert shown["web_evidence"] == []
    assert shown["github_status"] == "unchecked"
    assert "השם המלא" in (shown.get("web_note") or "")
    assert shown.get("linkedin_status") == "closed" or shown.get("linkedin_status") in (None, "not_provided")


def test_pdf_link_target_is_added_when_the_visible_text_has_none(tmp_path):
    from pypdf import PdfWriter
    from pypdf.annotations import Link

    from app.cv_text import enrich_stored_text

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_annotation(0, Link(rect=(0, 0, 100, 100), url="https://github.com/smerzel"))
    path = tmp_path / "cv.pdf"
    with path.open("wb") as handle:
        writer.write(handle)
    text = enrich_stored_text("Sara Merzel\nGitHub", str(path))
    assert "https://github.com/smerzel" in text


def test_health_reports_database_backend(client):
    body = client.get("/health").get_json()
    assert body["status"] == "ok"
    expected = "mssql" if os.getenv("TEST_DATABASE_URL") else "sqlite"
    assert body["database"]["backend"] == expected
    assert body["embeddings"]["model"] == "token-hash"
    assert set(body["database"]["counts"]) == {"events", "users", "jobs", "applications"}
