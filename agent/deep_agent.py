"""Candidate screening Deep Agent (LangChain `deepagents`).

The agent plans its own investigation and calls tools:
  - extract_resume_profile, evaluate_requirement_coverage  -> MCP Studio server (stdio)
  - tavily_web_search                                       -> Tavily MCP server
  - rag_cv_against_job                                      -> Chroma vector store

Every tool result is recorded in a trace. The final report is the agent's own
JSON, cross-checked against the trace: if the agent skipped a mandatory tool,
the tool is run and the report is flagged, so no score is ever invented.

FITSCREEN_AGENT_MODE=pipeline runs the same tools without an LLM. It exists for
the offline test suite only; the worker refuses to screen in that mode unless
it is set explicitly.
"""

from __future__ import annotations

import json
import os

from agent.mcp_client import call_studio_tool, call_tavily_search
from agent.rag import excerpts_for_application, similar_for_job

REQUIRED_TOOLS = (
    "extract_resume_profile",
    "evaluate_requirement_coverage",
    "rag_cv_against_job",
    "tavily_web_search",
)

SYSTEM_PROMPT = """You are FitScreen's candidate screening agent for an HR team.
You evaluate ONE job application. You must base every claim on tool output.

Mandatory investigation, in this order:
1. extract_resume_profile on the CV text.
2. evaluate_requirement_coverage with the job requirements and the CV.
3. rag_cv_against_job to get semantic fit and the CV passages most relevant to the job.
4. tavily_web_search at least once: verify the candidate's most recent employer, and
   check the job's core technology. Use the evidence, do not just list links.

Scoring:
- skill_coverage: take coverage_score from evaluate_requirement_coverage.
- semantic_fit: semantic_fit_percent from rag_cv_against_job.
- overall_score = round(0.45*skill_coverage + 0.35*semantic_fit + 0.20*web_score), where
  web_score is 0-100 for how well web evidence supports the CV (50 if inconclusive).
- recommendation: advance if overall_score >= 70, hold if 45-69, reject if below 45.

Finish with ONLY a JSON object, no prose, with keys:
overall_score (int), skill_coverage (int), semantic_fit (int), web_score (int),
recommendation ("advance"|"hold"|"reject"), summary (2-3 sentences for HR),
strengths (list of str), gaps (list of str),
web_evidence (list of {"title","url","finding"}), cv_excerpts (list of str)."""


class AgentNotConfigured(RuntimeError):
    pass


def agent_mode() -> str:
    return os.getenv("FITSCREEN_AGENT_MODE", "deepagent").strip().lower()


def llm_provider() -> str:
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider:
        return provider
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    return "none"


def describe_runtime() -> str:
    if agent_mode() == "pipeline":
        return "pipeline (tests only, no LLM)"
    return f"deepagents + {llm_provider()}"


def evaluate_application(application: dict) -> dict:
    if agent_mode() == "pipeline":
        return _run_pipeline(application)
    return _run_deep_agent(application)


def _build_model():
    provider = llm_provider()
    if provider == "gemini":
        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise AgentNotConfigured("LLM_PROVIDER=gemini but GEMINI_API_KEY is empty")
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            google_api_key=key,
            temperature=0,
        )
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            temperature=0,
        )
    raise AgentNotConfigured(
        "No LLM configured. Set GEMINI_API_KEY (LLM_PROVIDER=gemini) or run Ollama (LLM_PROVIDER=ollama)."
    )


def _make_tools(application: dict, trace: dict):
    job = {
        "id": application["job_id"],
        "title": application.get("job_title"),
        "description": application.get("job_description"),
        "must_have_skills": application.get("must_have_skills"),
    }
    job_text = f"{job['title']}. {job['description']}. Required: {job['must_have_skills']}"

    def extract_resume_profile(cv_text: str) -> dict:
        """Parse a CV into skills, years of experience, last company and a summary (MCP Studio tool)."""
        result = call_studio_tool("extract_resume_profile", {"cv_text": cv_text})
        trace["extract_resume_profile"] = result
        return result

    def evaluate_requirement_coverage(
        must_have_skills: str,
        cv_text: str,
        nice_to_have_skills: str = "",
        min_years: int = 0,
        years_experience: int | None = None,
    ) -> dict:
        """Score how well the CV covers must-have and nice-to-have job skills (MCP Studio tool)."""
        args = {
            "must_have_skills": must_have_skills,
            "nice_to_have_skills": nice_to_have_skills,
            "cv_text": cv_text,
            "min_years": int(min_years or 0),
        }
        if years_experience is not None:
            args["years_experience"] = int(years_experience)
        result = call_studio_tool("evaluate_requirement_coverage", args)
        trace["evaluate_requirement_coverage"] = result
        return result

    def rag_cv_against_job() -> dict:
        """Semantic fit of this CV against the job from the vector store, plus the most relevant CV passages."""
        matches = similar_for_job(job, limit=50)
        mine = next((m for m in matches if m["application_id"] == application["id"]), None)
        result = {
            "semantic_fit_percent": int(round(mine["score"] * 100)) if mine else None,
            "rank_among_applicants": (matches.index(mine) + 1) if mine else None,
            "applicants_indexed": len(matches),
            "relevant_cv_passages": excerpts_for_application(application["id"], job_text),
        }
        trace["rag_cv_against_job"] = result
        return result

    def tavily_web_search(query: str) -> dict:
        """Search the web through the Tavily MCP server. Use it to verify employers and technologies."""
        result = call_tavily_search(query)
        trace.setdefault("tavily_web_search", []).append({"query": query, **result})
        return {"ok": result.get("ok"), "results": result.get("results"), "error": result.get("error")}

    return [extract_resume_profile, evaluate_requirement_coverage, rag_cv_against_job, tavily_web_search]


def _application_brief(application: dict) -> str:
    return json.dumps(
        {
            "job_title": application.get("job_title"),
            "job_description": application.get("job_description"),
            "must_have_skills": application.get("must_have_skills"),
            "nice_to_have_skills": application.get("nice_to_have_skills"),
            "min_years": application.get("min_years"),
            "job_location": application.get("job_location"),
            "cv_text": (application.get("cv_text") or "")[:8000],
        },
        ensure_ascii=False,
    )


def _run_deep_agent(application: dict) -> dict:
    from deepagents import create_deep_agent

    trace: dict = {}
    agent = create_deep_agent(
        model=_build_model(),
        tools=_make_tools(application, trace),
        system_prompt=SYSTEM_PROMPT,
    )
    state = agent.invoke(
        {"messages": [{"role": "user", "content": f"Screen this application:\n{_application_brief(application)}"}]},
        config={"recursion_limit": 60},
    )
    report = _extract_json(_final_text(state))
    return _finalize(report, trace, application, runtime=f"deepagents:{llm_provider()}")


def _final_text(state: dict) -> str:
    for message in reversed(state.get("messages", [])):
        if getattr(message, "type", "") != "ai":
            continue
        content = message.content
        if isinstance(content, list):
            content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
        if content and "{" in content:
            return content
    raise ValueError("Deep Agent finished without a JSON report")


def _extract_json(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Deep Agent did not return JSON")
    return json.loads(text[start : end + 1])


def _run_pipeline(application: dict) -> dict:
    trace: dict = {}
    tools = {fn.__name__: fn for fn in _make_tools(application, trace)}
    cv_text = application.get("cv_text") or ""
    profile = tools["extract_resume_profile"](cv_text)
    tools["evaluate_requirement_coverage"](
        application.get("must_have_skills") or "",
        cv_text,
        application.get("nice_to_have_skills") or "",
        int(application.get("min_years") or 0),
        profile.get("years_experience"),
    )
    tools["rag_cv_against_job"]()
    if profile.get("last_company"):
        tools["tavily_web_search"](str(profile["last_company"]))
    first_skill = (application.get("must_have_skills") or "").split(",")[0].strip()
    if first_skill:
        tools["tavily_web_search"](f"{first_skill} software engineering skills")
    return _finalize({}, trace, application, runtime="pipeline")


def _finalize(report: dict, trace: dict, application: dict, runtime: str) -> dict:
    """Make the report consistent with what the tools actually returned."""
    skipped = [name for name in REQUIRED_TOOLS if name not in trace]
    if skipped:
        tools = {fn.__name__: fn for fn in _make_tools(application, trace)}
        cv_text = application.get("cv_text") or ""
        if "extract_resume_profile" in skipped:
            tools["extract_resume_profile"](cv_text)
        if "evaluate_requirement_coverage" in skipped:
            tools["evaluate_requirement_coverage"](
                application.get("must_have_skills") or "",
                cv_text,
                application.get("nice_to_have_skills") or "",
                int(application.get("min_years") or 0),
            )
        if "rag_cv_against_job" in skipped:
            tools["rag_cv_against_job"]()
        if "tavily_web_search" in skipped:
            tools["tavily_web_search"](f"{application.get('job_title','')} {application.get('must_have_skills','')}")

    coverage = trace.get("evaluate_requirement_coverage") or {}
    rag = trace.get("rag_cv_against_job") or {}
    searches = trace.get("tavily_web_search") or []
    web_hits = [r for s in searches if s.get("ok") for r in (s.get("results") or [])]
    web_errors = [s.get("error") for s in searches if not s.get("ok")]

    skill_coverage = int(coverage.get("coverage_score") or 0)
    semantic_fit = rag.get("semantic_fit_percent")
    semantic_fit = int(semantic_fit) if semantic_fit is not None else 50
    web_available = bool(web_hits)
    web_score = int(report.get("web_score", 60 if web_available else 50))
    if web_available or web_errors == []:
        overall = round(0.45 * skill_coverage + 0.35 * semantic_fit + 0.20 * web_score)
    else:
        # Web search failed: reweight the evidence we do have instead of guessing.
        overall = round(0.56 * skill_coverage + 0.44 * semantic_fit)
    overall = max(0, min(100, int(overall)))
    recommendation = "advance" if overall >= 70 else "hold" if overall >= 45 else "reject"

    strengths = report.get("strengths") or (
        list(coverage.get("must_have_matched") or []) + list(coverage.get("nice_to_have_matched") or [])
    )
    gaps = list(report.get("gaps") or coverage.get("must_have_missing") or [])
    if web_errors and not web_available:
        gaps.append("Web verification (Tavily MCP) did not complete: " + "; ".join(e for e in web_errors if e)[:200])

    web_evidence = report.get("web_evidence") or [
        {"title": h.get("title", ""), "url": h.get("url", ""), "finding": (h.get("content") or "")[:240]}
        for h in web_hits[:5]
        if isinstance(h, dict)
    ]

    return {
        "overall_score": overall,
        "skill_coverage": skill_coverage,
        "semantic_fit": semantic_fit,
        "web_score": web_score if web_available else None,
        "recommendation": recommendation,
        "agent_recommendation": report.get("recommendation"),
        "summary": report.get("summary", ""),
        "strengths": list(strengths)[:8],
        "gaps": gaps[:8],
        "web_evidence": web_evidence,
        "cv_excerpts": report.get("cv_excerpts") or rag.get("relevant_cv_passages") or [],
        "profile": trace.get("extract_resume_profile") or {},
        "tools_used": [name for name in REQUIRED_TOOLS if name in trace],
        "tools_skipped_by_agent": skipped,
        "runtime": runtime,
    }
