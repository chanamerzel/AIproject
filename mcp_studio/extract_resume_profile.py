from __future__ import annotations

import re

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
YEARS_RE = re.compile(
    r"(\d+)\s*(?:\+)?\s*(?:years?|yrs?|שנות|שנים)",
    re.I,
)
SKILL_LEXICON = {
    "python",
    "java",
    "javascript",
    "typescript",
    "flask",
    "django",
    "fastapi",
    "sql",
    "postgresql",
    "mysql",
    "sqlite",
    "docker",
    "kubernetes",
    "aws",
    "azure",
    "gcp",
    "react",
    "vue",
    "node",
    "linux",
    "git",
    "chromadb",
    "chroma",
    "rag",
    "llm",
    "pandas",
    "numpy",
    "pytest",
    "rest",
    "cqrs",
    "html",
    "css",
}


def extract_resume_profile(cv_text: str) -> dict:
    text = cv_text or ""
    emails = EMAIL_RE.findall(text)
    years = [int(m.group(1)) for m in YEARS_RE.finditer(text)]
    tokens = {t.strip(".,;:()[]").lower() for t in re.split(r"[\s,/|]+", text) if t}
    skills = sorted(tokens & SKILL_LEXICON)
    first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    last_company = _guess_company(text)
    return {
        "name_guess": first_line[:80],
        "emails": emails[:3],
        "skills": skills,
        "years_experience": max(years) if years else None,
        "last_company": last_company,
        "summary": text[:400].strip(),
    }


def _guess_company(text: str) -> str | None:
    for line in text.splitlines():
        low = line.lower()
        if "at " in low or "חברה" in low or "company" in low:
            return line.strip()[:120]
    return None
