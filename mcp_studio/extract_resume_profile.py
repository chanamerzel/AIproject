from __future__ import annotations

import re

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
YEARS_RE = re.compile(
    r"(\d+)\s*(?:\+)?\s*(?:years?|yrs?|שנות|שנים)",
    re.I,
)
GITHUB_RE = re.compile(
    r"(https?://(?:www\.)?github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))(?:/[A-Za-z0-9._-]+)?)",
    re.I,
)
LINKEDIN_RE = re.compile(
    r"https?://(?:[\w.]+\.)?linkedin\.com/in/([A-Za-z0-9\-_%]+)",
    re.I,
)
COMPANY_RE = re.compile(r"\bat\s+([A-Z][A-Za-z0-9&.\-]*[A-Za-z0-9])")
HEBREW_COMPANY_RE = re.compile(r"בחברת\s+(\S+)")
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
    github = GITHUB_RE.search(text)
    linkedin = LINKEDIN_RE.search(text)
    return {
        "name_guess": first_line[:80],
        "emails": emails[:3],
        "skills": skills,
        "years_experience": max(years) if years else None,
        "last_company": _guess_company(text),
        "github_url": github.group(1) if github else None,
        "github_login": github.group(2) if github else None,
        "linkedin_url": linkedin.group(0) if linkedin else None,
        "summary": text[:400].strip(),
    }


def _guess_company(text: str) -> str | None:
    match = COMPANY_RE.search(text)
    if match:
        return match.group(1)[:120]
    for line in text.splitlines():
        hebrew = HEBREW_COMPANY_RE.search(line)
        if hebrew:
            return hebrew.group(1).strip(".,")[:120]
    return None
