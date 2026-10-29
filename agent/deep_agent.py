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
Use tavily_web_search (1 to 3 searches) to find public pages about THIS PERSON, in this order:
1. The quoted full name (example: "Sara Merzel").
2. The quoted full name plus last employer, when the CV has one.
3. The quoted full name plus the job title.
Do not search a GitHub or LinkedIn URL. Do not search a technology by itself (Python, Flask, ...).
LinkedIn is closed; do not try to open it. Reply with findings, each with its source URL. Never invent URLs."""

SYSTEM_PROMPT = """You are FitScreen's screening orchestrator for an HR team.
You evaluate ONE job application. You do not call screening tools yourself;
you delegate with the `task` tool:
- `cv-analyst`: analyses the CV against the job (skills, experience, semantic fit).
- `web-researcher`: searches the public web for the candidate's quoted full name.

Steps:
1. Write a short todo plan.
2. Delegate to cv-analyst.
3. Delegate to web-researcher. Give it the candidate's full name, last company, and job title.
   It must search the quoted full name. It must not search GitHub URLs, LinkedIn, or a technology alone.
4. Combine both answers.

Scoring (the system overwrites these from tool output; still include them):
- skill_coverage: coverage_score reported by cv-analyst.
- semantic_fit: semantic_fit_percent reported by cv-analyst.
- web_score: public pages that name the candidate, plus overlap between their GitHub languages and the job.
- overall_score = round(0.45*skill_coverage + 0.35*semantic_fit + 0.20*web_score).
- recommendation: advance if overall_score >= 70, hold if 45-69, reject if below 45.

Finish with ONLY a JSON object, no prose, with keys:
overall_score (int), skill_coverage (int), semantic_fit (int), web_score (int),
recommendation ("advance"|"hold"|"reject"), summary (2-3 sentences in Hebrew for HR),
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
        """Search the public web through the Tavily MCP server for this candidate's quoted full name."""
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
            "description": "Searches the public web for the candidate's quoted full name, then the name plus employer or job title.",
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
            "candidate_name": application.get("candidate_name"),
            "candidate_email": application.get("candidate_email"),
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
    for query in _web_queries(profile, application):
        tools["tavily_web_search"](query)
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
                profile = trace.get("extract_resume_profile") or {}
                queries = _web_queries(profile, application)
                if queries:
                    tools[name](queries[0])
                else:
                    trace["tavily_web_search"] = [{"query": "", "ok": True, "results": []}]
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
    profile = trace.get("extract_resume_profile") or {}
    github = _github_report(profile, application.get("must_have_skills") or "")
    hits = [h for h in web_hits if isinstance(h, dict) and h.get("url")]
    relevant_hits = [h for h in hits if _about_candidate(h, profile, application)]
    web_evidence = [{"title": h.get("title") or h["url"], "url": h["url"]} for h in relevant_hits[:5]]
    tavily_ok = any(s.get("ok") for s in searches)
    tavily_score = _tavily_score(relevant_hits, profile) if tavily_ok or web_hits else None
    github_score = github.get("github_score")
    if tavily_score is None and github_score is None:
        web_score = None
        web_note = ""
    elif github_score is None:
        web_score = tavily_score
        web_note = "" if relevant_hits else "חיפשנו את השם המלא ברשת ולא מצאנו נוכחות ציבורית."
    elif tavily_score is None:
        web_score = github_score
        web_note = ""
    else:
        web_score = round(0.5 * tavily_score + 0.5 * github_score)
        web_note = "" if relevant_hits else "חיפשנו את השם המלא ברשת ולא מצאנו נוכחות ציבורית."
    if web_score is None:
        overall = round(0.56 * skill_coverage + 0.44 * semantic_fit)
    else:
        overall = round(0.45 * skill_coverage + 0.35 * semantic_fit + 0.20 * web_score)
    overall = max(0, min(100, int(overall)))
    recommendation = "advance" if overall >= 70 else "hold" if overall >= 45 else "reject"

    strengths = report.get("strengths") or (
        list(coverage.get("must_have_matched") or []) + list(coverage.get("nice_to_have_matched") or [])
    )
    gaps = list(coverage.get("must_have_missing") or report.get("gaps") or [])
    if web_errors and not tavily_ok:
        gaps.append("חיפוש השם ברשת לא הושלם")

    summary = report.get("summary") or _fallback_summary(coverage, semantic_fit, len(relevant_hits))

    calls = trace.get("_calls") or []
    return {
        "overall_score": overall,
        "skill_coverage": skill_coverage,
        "semantic_fit": semantic_fit,
        "web_score": web_score,
        "recommendation": recommendation,
        "agent_recommendation": report.get("recommendation"),
        "summary": summary,
        "strengths": [str(s) for s in strengths][:8],
        "gaps": [str(g) for g in gaps][:8],
        "web_evidence": web_evidence[:5],
        "web_note": web_note,
        "cv_excerpts": report.get("cv_excerpts") or rag.get("relevant_cv_passages") or [],
        "must_have_missing": list(coverage.get("must_have_missing") or []),
        "github_status": github["github_status"],
        "github_portfolio": github.get("github_portfolio"),
        "linkedin_status": _linkedin_status(profile),
        "profile": profile,
        "tools_used": [name for name in REQUIRED_TOOLS if name in trace],
        "tools_skipped_by_agent": skipped,
        "delegation": [c for c in calls if c["by"] != "reconciliation"],
        "agent_state": _agent_state(calls, coverage, rag, web_evidence, overall, trace),
        "runtime": runtime,
    }


_PLAN = (
    ("extract_resume_profile", "חילוץ פרופיל מקורות החיים"),
    ("evaluate_requirement_coverage", "בדיקת כיסוי דרישות המשרה"),
    ("rag_cv_against_job", "אחזור קטעים מהמסד הווקטורי"),
    ("tavily_web_search", "חיפוש השם ברשת"),
)


def _agent_state(calls: list, coverage: dict, rag: dict, web_evidence: list, overall: int, trace: dict) -> dict:
    """The screening state from lesson 7: plan, step, tool calls, citations."""
    done = {c["tool"] for c in calls} | {name for name, _label in _PLAN if name in trace}
    plan = [{"step": label, "tool": tool, "done": tool in done} for tool, label in _PLAN]
    visible_calls = [c for c in calls if c.get("by") != "reconciliation"]
    citations = [
        {
            "kind": "skill",
            "label": item.get("skill"),
            "quote": item.get("quote"),
            "matched": bool(item.get("matched")),
        }
        for item in (coverage.get("skill_evidence") or [])
    ]
    finished = sum(1 for item in plan if item["done"])
    return {
        "plan": plan,
        "current_step": finished,
        "step_count": len(plan),
        "tool_calls": [{"tool": c["tool"], "by": c["by"]} for c in visible_calls],
        "citations": citations[:12],
        "confidence": overall,
    }


def state_for_saved_report(
    report: dict,
    cv_text: str,
    must_have: str,
    nice_to_have: str = "",
    candidate_name: str = "",
) -> dict:
    """Show a saved report with skill sentences and only web pages about this candidate."""
    if not report:
        return report
    from mcp_studio.extract_resume_profile import extract_resume_profile
    from mcp_studio.evaluate_requirement_coverage import evaluate_requirement_coverage

    filled = dict(report)
    profile = dict(filled.get("profile") or {})
    extracted = extract_resume_profile(cv_text or "")
    if extracted.get("github_url") and not profile.get("github_url"):
        profile["github_url"] = extracted["github_url"]
        profile["github_login"] = extracted.get("github_login")
        if filled.get("github_status") in (None, "not_provided"):
            filled["github_status"] = "unchecked"
    if extracted.get("linkedin_url") and not profile.get("linkedin_url"):
        profile["linkedin_url"] = extracted["linkedin_url"]
    filled["profile"] = profile
    if profile.get("linkedin_url"):
        filled["linkedin_status"] = "closed"
    application = {"candidate_name": candidate_name}
    original = [item for item in (filled.get("web_evidence") or []) if isinstance(item, dict)]
    relevant = [item for item in original if _about_candidate(item, profile, application)]
    filled["web_evidence"] = [
        {"title": item.get("title") or item.get("url"), "url": item.get("url")} for item in relevant[:5]
    ]
    github = _github_report(profile, must_have)
    if github.get("github_portfolio") or github["github_status"] != "not_provided":
        if github["github_status"] == "verified" or filled.get("github_status") in (None, "not_provided", "unchecked"):
            filled["github_status"] = github["github_status"]
        if github.get("github_portfolio"):
            filled["github_portfolio"] = github["github_portfolio"]
    if original and not filled["web_evidence"]:
        filled["web_note"] = "חיפשנו את השם המלא ברשת ולא מצאנו נוכחות ציבורית."
    elif filled["web_evidence"]:
        filled["web_note"] = ""
    coverage = evaluate_requirement_coverage(must_have or "", nice_to_have or "", cv_text or "")
    filled["skill_evidence"] = coverage.get("skill_evidence") or []
    inferred = []
    if profile:
        inferred.append("extract_resume_profile")
    if filled.get("skill_coverage") is not None:
        inferred.append("evaluate_requirement_coverage")
    if filled.get("cv_excerpts"):
        inferred.append("rag_cv_against_job")
    if original or filled.get("web_score") is not None:
        inferred.append("tavily_web_search")
    used = list(dict.fromkeys([*(filled.get("tools_used") or []), *inferred]))
    previous = filled.get("agent_state") or {}
    state = _agent_state(
        [{"tool": name, "by": "report"} for name in used],
        coverage,
        {"relevant_cv_passages": filled.get("cv_excerpts") or []},
        filled["web_evidence"],
        int(filled.get("overall_score") or 0),
        {name: {} for name in used},
    )
    if previous.get("plan"):
        state["plan"] = previous["plan"]
        state["current_step"] = previous.get("current_step", state["current_step"])
        state["tool_calls"] = previous.get("tool_calls") or state["tool_calls"]
    filled["agent_state"] = state
    return filled


def _fallback_summary(coverage: dict, semantic_fit: int, sources: int) -> str:
    matched = list(coverage.get("must_have_matched") or [])
    missing = list(coverage.get("must_have_missing") or [])
    total = len(matched) + len(missing)
    if total:
        text = f"קורות החיים מכסים {len(matched)} מתוך {total} כישורי חובה"
    else:
        text = "לא הוגדרו כישורי חובה למשרה"
    if missing:
        text += f" (חסר: {', '.join(missing)})"
    text += f". התאמה סמנטית למשרה: {semantic_fit}%."
    text += f" נמצאו {sources} מקורות ברשת." if sources else " לא נמצאו מקורות ברשת."
    return text + " (הסיכום חושב מתוצאות הכלים.)"


def _about_candidate(hit: dict, profile: dict, application: dict) -> bool:
    """A page counts only when it names the person or their public profile, not the employer alone."""
    blob = " ".join(
        str(hit.get(key) or "") for key in ("url", "title", "content", "finding")
    ).casefold()
    if not blob.strip():
        return False
    for term in _identity_terms(profile, application):
        if term in blob:
            return True
    return False


def _person_name(profile: dict, application: dict) -> str:
    raw = (application.get("candidate_name") or profile.get("name_guess") or "").strip()
    words = [word.strip(".,;:") for word in raw.replace(".", " ").split() if len(word.strip(".,;:")) >= 2]
    if len(words) >= 2:
        return " ".join(words[:3])
    return ""


def _identity_terms(profile: dict, application: dict) -> list[str]:
    terms = []
    name = _person_name(profile, application)
    if name:
        terms.append(name.casefold())
    login = (profile.get("github_login") or "").strip()
    if login:
        terms.append(f"github.com/{login}".casefold())
    linkedin = (profile.get("linkedin_url") or "").strip()
    if linkedin:
        terms.append(linkedin.casefold())
    email = ""
    emails = profile.get("emails") or []
    if emails:
        email = str(emails[0])
    elif application.get("candidate_email"):
        email = str(application["candidate_email"])
    if "@" in email:
        terms.append(email.casefold())
    return terms


def _hit_blob(hits: list) -> str:
    parts = []
    for hit in hits:
        if isinstance(hit, dict):
            parts.append(f"{hit.get('url', '')} {hit.get('title', '')} {hit.get('content', '')}")
    return " ".join(parts).casefold()


def _tavily_score(hits: list, profile: dict) -> int:
    if not hits:
        return 0
    score = 55
    company = (profile.get("last_company") or "").strip().casefold()
    if company and company in _hit_blob(hits):
        score += 35
    if len(hits) >= 2:
        score += 10
    return min(100, score)


def _skill_tokens(must_have: str) -> list[str]:
    return [part.strip() for part in (must_have or "").replace(";", ",").split(",") if part.strip()]


def _github_matched_skills(portfolio: dict, must_have: str) -> list[str]:
    repos = portfolio.get("repos") or []
    blob = " ".join(
        [
            *(portfolio.get("languages") or []),
            *(str(repo.get("language") or "") for repo in repos),
            *(str(repo.get("name") or "") for repo in repos),
            *(str(repo.get("description") or "") for repo in repos),
        ]
    ).casefold()
    aliases = {"js": "javascript", "node": "javascript", "ts": "typescript", "golang": "go"}
    matched = []
    for skill in _skill_tokens(must_have):
        needle = aliases.get(skill.casefold(), skill.casefold())
        if needle and needle in blob:
            matched.append(skill)
    return matched


def _github_score(portfolio: dict, must_have: str) -> int:
    repos = portfolio.get("repos") or []
    matched = portfolio.get("matched_skills") or _github_matched_skills(portfolio, must_have)
    if not repos and not portfolio.get("public_repos"):
        return 20
    score = 40
    if matched:
        score += min(60, 30 * len(matched))
    return min(100, score)


def _github_report(profile: dict, must_have: str) -> dict:
    from agent.github_public import inspect

    login = (profile.get("github_login") or "").strip()
    if not login:
        return {"github_status": "not_provided", "github_portfolio": None, "github_score": None}
    portfolio = inspect(login)
    if not portfolio:
        return {"github_status": "unchecked", "github_portfolio": None, "github_score": None}
    if not portfolio.get("ok"):
        return {"github_status": "not_found", "github_portfolio": {"ok": False, "login": login}, "github_score": 0}
    matched = _github_matched_skills(portfolio, must_have)
    filled = {**portfolio, "matched_skills": matched}
    return {"github_status": "verified", "github_portfolio": filled, "github_score": _github_score(filled, must_have)}


def _linkedin_status(profile: dict) -> str:
    if (profile.get("linkedin_url") or "").strip():
        return "closed"
    return "not_provided"


def _web_queries(profile: dict, application: dict) -> list[str]:
    name = _person_name(profile, application)
    if not name:
        return []
    queries = [f'"{name}"']
    company = (profile.get("last_company") or "").strip()
    if company:
        queries.append(f'"{name}" {company}')
    title = (application.get("job_title") or "").strip()
    if title:
        queries.append(f'"{name}" {title}')
    return queries[:3]

