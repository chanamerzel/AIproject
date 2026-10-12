"""Candidate screening Deep Agent (LangChain `deepagents`).

An orchestrator agent plans the screening (write_todos) and delegates to two
subagents through the deepagents `task` tool:
  - cv-analyst      -> extract_resume_profile, evaluate_requirement_coverage (MCP Studio, stdio)
                       and rag_cv_against_job (Chroma vector store)
  - web-researcher  -> tavily_web_search (Tavily MCP server)

Every tool result is recorded in a trace together with the agent that called
it. The final report is the orchestrator's JSON, cross-checked against the
trace: if a mandatory tool was skipped it is run and the report is flagged, so
no score is ever invented.

Model selection (LLM_PROVIDER): gemini, ollama, or auto (default) which uses
Gemini and falls back to a local Ollama (when it is up with the model pulled)
if Gemini has no key or the run fails.

FITSCREEN_AGENT_MODE=pipeline runs the same tools without an LLM. It exists for
the offline test suite only.
"""

from __future__ import annotations

import json
import logging
import os

import httpx

from agent.mcp_client import call_studio_tool, call_tavily_search
from agent.rag import excerpts_for_application, similar_for_job

logger = logging.getLogger("fitscreen.agent")

REQUIRED_TOOLS = (
    "extract_resume_profile",
    "evaluate_requirement_coverage",
    "rag_cv_against_job",
    "tavily_web_search",
)

CV_ANALYST_PROMPT = """You are the CV analyst of an HR screening team.
The CV and the job are already loaded into your tools; they take no CV input.
Call, in this order:
1. extract_resume_profile
2. evaluate_requirement_coverage
3. rag_cv_against_job
Then reply with a short factual summary: matched and missing must-have skills,
years of experience, last company, coverage_score, semantic_fit_percent, and the
two most relevant CV passages. Use only tool output."""

WEB_RESEARCHER_PROMPT = """You are the web researcher of an HR screening team.
Use tavily_web_search (1 to 3 searches) to check what you were asked: whether the
candidate's most recent employer is a real company in the stated field, and what
the job's core technology involves. Reply with findings, each with its source URL.
Say clearly when the evidence is inconclusive. Never invent URLs."""

SYSTEM_PROMPT = """You are FitScreen's screening orchestrator for an HR team.
You evaluate ONE job application. You do not call screening tools yourself;
you delegate with the `task` tool:
- `cv-analyst`: analyses the CV against the job (skills, experience, semantic fit).
- `web-researcher`: verifies the candidate's last employer and the job's core technology on the web.

Steps:
1. Write a short todo plan.
2. Delegate to cv-analyst.
3. Delegate to web-researcher, naming the last company from the CV analysis and the job's main skill.
4. Combine both answers.

Scoring:
- skill_coverage: coverage_score reported by cv-analyst.
- semantic_fit: semantic_fit_percent reported by cv-analyst.
- web_score: 0-100 for how well web evidence supports the CV (50 if inconclusive).
- overall_score = round(0.45*skill_coverage + 0.35*semantic_fit + 0.20*web_score).
- recommendation: advance if overall_score >= 70, hold if 45-69, reject if below 45.

Finish with ONLY a JSON object, no prose, with keys:
overall_score (int), skill_coverage (int), semantic_fit (int), web_score (int),
recommendation ("advance"|"hold"|"reject"), summary (2-3 sentences for HR),
strengths (list of str), gaps (list of str),
web_evidence (list of {"title","url","finding"}), cv_excerpts (list of str)."""


DEFAULT_GEMINI_MODELS = "gemini-2.5-flash,gemini-3.5-flash,gemini-2.5-flash-lite,gemini-3.1-flash-lite"


class AgentNotConfigured(RuntimeError):
    pass


def agent_mode() -> str:
    return os.getenv("FITSCREEN_AGENT_MODE", "deepagent").strip().lower()


def llm_provider() -> str:
    return os.getenv("LLM_PROVIDER", "").strip().lower() or "auto"


def describe_runtime() -> str:
    if agent_mode() == "pipeline":
        return "pipeline (tests only, no LLM)"
    provider = llm_provider()
    if provider == "auto":
        return "deepagents + auto (gemini, then ollama)"
    return f"deepagents + {provider}"


def evaluate_application(application: dict) -> dict:
    if agent_mode() == "pipeline":
        return _run_pipeline(application)
    return _run_deep_agent(application)


def _ollama_settings() -> tuple[str, str]:
    base = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    return base, os.getenv("OLLAMA_MODEL", "qwen2.5:3b")


def ollama_status() -> str | None:
    """None when Ollama answers and the model is pulled, otherwise the reason."""
    base, model = _ollama_settings()
    try:
        response = httpx.get(f"{base}/api/tags", timeout=3)
        response.raise_for_status()
        names = {m.get("name") for m in response.json().get("models", [])}
    except Exception as exc:
        return f"Ollama not reachable at {base} ({type(exc).__name__})"
    if model not in names and f"{model}:latest" not in names:
        return f"Ollama model {model} is not pulled (ollama pull {model})"
    return None


def _gemini_key() -> str:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""


def gemini_models() -> list[str]:
    """GEMINI_MODEL may list several models; each has its own free-tier daily quota."""
    raw = os.getenv("GEMINI_MODEL", "") or DEFAULT_GEMINI_MODELS
    return [m.strip() for m in raw.split(",") if m.strip()]


def _build_model(provider: str, model_name: str | None = None):
    if provider == "gemini":
        if not _gemini_key():
            raise AgentNotConfigured("GEMINI_API_KEY is empty")
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_name or gemini_models()[0],
            google_api_key=_gemini_key(),
            temperature=0,
            # Fail fast on an exhausted quota so the next model in the chain is tried.
            max_retries=1,
        )
    if provider == "ollama":
        reason = ollama_status()
        if reason:
            raise AgentNotConfigured(reason)
        from langchain_ollama import ChatOllama

        base, model = _ollama_settings()
        return ChatOllama(
            model=model,
            base_url=base,
            temperature=0,
            # deepagents' built-in prompt and tool schemas do not fit Ollama's default context.
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "16384")),
        )
    raise AgentNotConfigured(f"Unknown LLM_PROVIDER={provider}")


def model_chain() -> list[tuple[str, object]]:
    """Models to try in order. Raises AgentNotConfigured when none is usable."""
    provider = llm_provider()
    order = ["gemini", "ollama"] if provider == "auto" else [provider]
    chain, reasons = [], []
    for name in order:
        try:
            if name == "gemini":
                chain.extend((name, _build_model(name, model)) for model in gemini_models())
            else:
                chain.append((name, _build_model(name)))
        except AgentNotConfigured as exc:
            reasons.append(f"{name}: {exc}")
    if not chain:
        raise AgentNotConfigured("No LLM configured (" + "; ".join(reasons) + ")")
    return chain


def _make_tools(application: dict, trace: dict, caller: str):
    job = {
        "id": application["job_id"],
        "title": application.get("job_title"),
        "description": application.get("job_description"),
        "must_have_skills": application.get("must_have_skills"),
    }
    job_text = f"{job['title']}. {job['description']}. Required: {job['must_have_skills']}"
    cv_text = application.get("cv_text") or ""

    def record(name: str, result):
        trace.setdefault("_calls", []).append({"tool": name, "by": caller})
        return result

    def extract_resume_profile() -> dict:
        """Parse the applicant's CV into skills, years of experience, last company and a summary (MCP Studio tool)."""
        result = call_studio_tool("extract_resume_profile", {"cv_text": cv_text})
        trace["extract_resume_profile"] = result
        return record("extract_resume_profile", result)

    def evaluate_requirement_coverage() -> dict:
        """Score how well the CV covers the job's must-have and nice-to-have skills (MCP Studio tool)."""
        args = {
            "must_have_skills": application.get("must_have_skills") or "",
            "nice_to_have_skills": application.get("nice_to_have_skills") or "",
            "cv_text": cv_text,
            "min_years": int(application.get("min_years") or 0),
        }
        years = (trace.get("extract_resume_profile") or {}).get("years_experience")
        if years is not None:
            args["years_experience"] = int(years)
        result = call_studio_tool("evaluate_requirement_coverage", args)
        trace["evaluate_requirement_coverage"] = result
        return record("evaluate_requirement_coverage", result)

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
        return record("rag_cv_against_job", result)

    def tavily_web_search(query: str) -> dict:
        """Search the web through the Tavily MCP server. Use it to verify employers and technologies."""
        result = call_tavily_search(query)
        trace.setdefault("tavily_web_search", []).append({"query": query, **result})
        record("tavily_web_search", None)
        return {"ok": result.get("ok"), "results": result.get("results"), "error": result.get("error")}

    return {
        "extract_resume_profile": extract_resume_profile,
        "evaluate_requirement_coverage": evaluate_requirement_coverage,
        "rag_cv_against_job": rag_cv_against_job,
        "tavily_web_search": tavily_web_search,
    }


def _subagents(application: dict, trace: dict) -> list[dict]:
    analyst = _make_tools(application, trace, "cv-analyst")
    researcher = _make_tools(application, trace, "web-researcher")
    return [
        {
            "name": "cv-analyst",
            "description": "Analyses the applicant's CV against the job: skills coverage, experience and semantic fit from the vector store.",
            "system_prompt": CV_ANALYST_PROMPT,
            "tools": [
                analyst["extract_resume_profile"],
                analyst["evaluate_requirement_coverage"],
                analyst["rag_cv_against_job"],
            ],
        },
        {
            "name": "web-researcher",
            "description": "Verifies the candidate's last employer and the job's core technology with web search.",
            "system_prompt": WEB_RESEARCHER_PROMPT,
            "tools": [researcher["tavily_web_search"]],
        },
    ]


def _application_brief(application: dict) -> str:
    return json.dumps(
        {
            "job_title": application.get("job_title"),
            "job_description": application.get("job_description"),
            "must_have_skills": application.get("must_have_skills"),
            "nice_to_have_skills": application.get("nice_to_have_skills"),
            "min_years": application.get("min_years"),
            "job_location": application.get("job_location"),
            "cv_text": (application.get("cv_text") or "")[:6000],
        },
        ensure_ascii=False,
    )


def _run_deep_agent(application: dict) -> dict:
    last_error: Exception | None = None
    for provider, model in model_chain():
        try:
            return _run_with_model(application, model, provider)
        except Exception as exc:
            logger.warning("deep agent with %s failed: %s: %s", provider, type(exc).__name__, exc)
            last_error = exc
    raise last_error


def _run_with_model(application: dict, model, provider: str) -> dict:
    from deepagents import create_deep_agent

    trace: dict = {}
    agent = create_deep_agent(
        model=model,
        tools=[],
        system_prompt=SYSTEM_PROMPT,
        subagents=_subagents(application, trace),
    )
    state = agent.invoke(
        {"messages": [{"role": "user", "content": f"Screen this application:\n{_application_brief(application)}"}]},
        config={"recursion_limit": 80},
    )
    try:
        report = _extract_json(_final_text(state))
        report_valid = True
    except ValueError:
        report, report_valid = {}, False
    result = _finalize(report, trace, application, runtime=f"deepagents:{_model_label(model, provider)}")
    result["agent_report_valid"] = report_valid
    return result


def _model_label(model, provider: str) -> str:
    name = getattr(model, "model", None) or getattr(model, "model_name", None)
    return f"{provider}:{name}" if name else provider


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
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Deep Agent returned invalid JSON: {exc}") from exc


def _run_pipeline(application: dict) -> dict:
    trace: dict = {}
    tools = _make_tools(application, trace, "pipeline")
    profile = tools["extract_resume_profile"]()
    tools["evaluate_requirement_coverage"]()
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
        tools = _make_tools(application, trace, "reconciliation")
        for name in REQUIRED_TOOLS:
            if name not in skipped:
                continue
            if name == "tavily_web_search":
                tools[name](f"{application.get('job_title', '')} {application.get('must_have_skills', '')}")
            else:
                tools[name]()

    coverage = trace.get("evaluate_requirement_coverage") or {}
    rag = trace.get("rag_cv_against_job") or {}
    searches = trace.get("tavily_web_search") or []
    web_hits = [r for s in searches if s.get("ok") for r in (s.get("results") or [])]
    web_errors = [s.get("error") for s in searches if not s.get("ok")]

    skill_coverage = int(coverage.get("coverage_score") or 0)
    semantic_fit = rag.get("semantic_fit_percent")
    semantic_fit = int(semantic_fit) if semantic_fit is not None else 50
    web_available = bool(web_hits)
    web_score = _clamp(report.get("web_score"), 60 if web_available else 50)
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

    hits = [h for h in web_hits if isinstance(h, dict) and h.get("url")]
    real_urls = {h["url"] for h in hits}
    # Keep the model's findings only for URLs Tavily actually returned; never show an invented link.
    web_evidence = [
        e for e in (report.get("web_evidence") or []) if isinstance(e, dict) and e.get("url") in real_urls
    ] or [
        {"title": h.get("title", ""), "url": h["url"], "finding": (h.get("content") or "")[:240]}
        for h in hits[:5]
    ]

    summary = report.get("summary") or _fallback_summary(coverage, semantic_fit, len(real_urls))

    calls = trace.get("_calls") or []
    return {
        "overall_score": overall,
        "skill_coverage": skill_coverage,
        "semantic_fit": semantic_fit,
        "web_score": web_score if web_available else None,
        "recommendation": recommendation,
        "agent_recommendation": report.get("recommendation"),
        "summary": summary,
        "strengths": [str(s) for s in strengths][:8],
        "gaps": [str(g) for g in gaps][:8],
        "web_evidence": web_evidence[:5],
        "cv_excerpts": report.get("cv_excerpts") or rag.get("relevant_cv_passages") or [],
        "profile": trace.get("extract_resume_profile") or {},
        "tools_used": [name for name in REQUIRED_TOOLS if name in trace],
        "tools_skipped_by_agent": skipped,
        "delegation": [c for c in calls if c["by"] != "reconciliation"],
        "runtime": runtime,
    }


def _fallback_summary(coverage: dict, semantic_fit: int, sources: int) -> str:
    matched = list(coverage.get("must_have_matched") or [])
    missing = list(coverage.get("must_have_missing") or [])
    total = len(matched) + len(missing)
    text = f"Covers {len(matched)} of {total} must-have skills" if total else "No must-have skills listed"
    if missing:
        text += f" (missing: {', '.join(missing)})"
    text += f". Semantic fit to the job: {semantic_fit}%."
    text += f" Web check: {sources} source(s)." if sources else " Web check returned no sources."
    return text + " (Generated from tool results: the agent did not write a summary.)"


def _clamp(value, default: int) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return default
