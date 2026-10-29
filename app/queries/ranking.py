"""F9: rank a job's applicants by the agent's score, with live vector similarity as tie-breaker.

Read-only: applications projection + Chroma. Applicants the agent has not screened
yet are still ranked by semantic similarity, after the screened ones.
"""

import json

from app.queries.applications import list_for_job

RECOMMENDATION_ORDER = {"advance": 0, "hold": 1, "reject": 2}


def _missing_skills(report: dict) -> list:
    missing = report.get("must_have_missing")
    if not isinstance(missing, list):
        missing = [g for g in report.get("gaps") or [] if "Tavily" not in str(g)]
    return [str(item) for item in missing if item][:3]


def ranking_for_job(job: dict) -> dict:
    from agent.rag import similar_for_job

    rows = list_for_job(job["id"], shape="ranking")
    similarity = {m["application_id"]: m["score"] for m in similar_for_job(job, limit=max(len(rows), 1))}

    ranked = []
    for row in rows:
        report = json.loads(row["agent_report_json"]) if row.get("agent_report_json") else {}
        semantic_live = similarity.get(row["id"])
        ranked.append(
            {
                "application_id": row["id"],
                "candidate_name": row["candidate_name"],
                "status": row["status"],
                "overall_score": row.get("agent_score"),
                "skill_coverage": report.get("skill_coverage"),
                "semantic_fit": report.get("semantic_fit"),
                "web_score": report.get("web_score"),
                "recommendation": report.get("recommendation"),
                "semantic_live": round(semantic_live * 100) if semantic_live is not None else None,
                "missing_skills": _missing_skills(report),
            }
        )

    ranked.sort(
        key=lambda r: (
            r["overall_score"] is None,
            -(r["overall_score"] or 0),
            -(r["semantic_live"] or 0),
        )
    )
    for position, item in enumerate(ranked, start=1):
        item["rank"] = position

    summary = {key: 0 for key in RECOMMENDATION_ORDER}
    for item in ranked:
        if item["recommendation"] in summary:
            summary[item["recommendation"]] += 1
    return {
        "items": ranked,
        "summary": summary,
        "screened": sum(1 for r in ranked if r["overall_score"] is not None),
        "total": len(ranked),
    }
