def similar_candidates_for_job(job: dict, limit: int = 8) -> list[dict]:
    from agent.rag import similar_for_job
    from app.queries.applications import get_application

    matches = similar_for_job(job, limit=limit)
    for match in matches:
        row = get_application(match["application_id"])
        match["candidate_name"] = row["candidate_name"] if row else match["application_id"]
    return matches
