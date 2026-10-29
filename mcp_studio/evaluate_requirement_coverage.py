from __future__ import annotations

import re
from functools import lru_cache

_PIECES = re.compile(r"[\n\r]+|(?<=[.!?])\s+")


def _split_skills(raw: str) -> list[str]:
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


@lru_cache(maxsize=256)
def _skill_pattern(skill: str) -> re.Pattern[str]:
    return re.compile(r"(?<!\w)" + re.escape(skill) + r"(?!\w)", re.IGNORECASE)


def _contains_skill(cv: str, skill: str) -> bool:
    """Match a whole skill, so Java does not count inside JavaScript."""
    return _skill_pattern(skill).search(cv) is not None


def _quote_for(pieces: list[str], skill: str) -> str | None:
    pattern = _skill_pattern(skill)
    for line in pieces:
        if line and pattern.search(line):
            return line[:240]
    return None


def evaluate_requirement_coverage(
    must_have_skills: str,
    nice_to_have_skills: str,
    cv_text: str,
    min_years: int = 0,
    years_experience: int | None = None,
) -> dict:
    cv = cv_text or ""
    must = _split_skills(must_have_skills)
    nice = _split_skills(nice_to_have_skills)
    pieces = [part.strip() for part in _PIECES.split(cv)]

    must_matched = []
    must_missing = []
    skill_evidence = []
    for skill in must:
        matched = _contains_skill(cv, skill)
        if matched:
            must_matched.append(skill)
        else:
            must_missing.append(skill)
        skill_evidence.append({"skill": skill, "matched": matched, "quote": _quote_for(pieces, skill)})
    nice_matched = [s for s in nice if _contains_skill(cv, s)]

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
        "skill_evidence": skill_evidence,
        "coverage_score": coverage,
        "years_ok": years_ok,
    }
