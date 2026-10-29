def similar_candidates_for_job(job: dict, limit: int = 8) -> list[dict]:
    from agent.rag import similar_for_job
    from app.queries.applications import names_by_application

    matches = similar_for_job(job, limit=limit)
    names = names_by_application([match["application_id"] for match in matches])
    for match in matches:
        name = names.get(match["application_id"])
        match["candidate_name"] = name if name is not None else match["application_id"]
    return matches
