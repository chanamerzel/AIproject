from __future__ import annotations


def _split_skills(raw: str) -> list[str]:
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


def evaluate_requirement_coverage(
    must_have_skills: str,
    nice_to_have_skills: str,
    cv_text: str,
    min_years: int = 0,
    years_experience: int | None = None,
) -> dict:
    cv = (cv_text or "").lower()
    must = _split_skills(must_have_skills)
    nice = _split_skills(nice_to_have_skills)

    must_matched = [s for s in must if s.lower() in cv]
    must_missing = [s for s in must if s.lower() not in cv]
    nice_matched = [s for s in nice if s.lower() in cv]

    if must:
        coverage = round(100 * len(must_matched) / len(must))
    else:
        coverage = 50

    years_ok = True
    if min_years and years_experience is not None:
        years_ok = years_experience >= int(min_years)
        if not years_ok:
            coverage = max(0, coverage - 15)

    return {
        "must_have_matched": must_matched,
        "must_have_missing": must_missing,
        "nice_to_have_matched": nice_matched,
        "coverage_score": coverage,
        "years_ok": years_ok,
    }
