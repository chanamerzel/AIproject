"""Public GitHub profile and repos. No login. Used when the CV has a github.com URL."""

from __future__ import annotations

import os
import re
import time

import httpx

_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "FitScreen"}
_CACHE_SECONDS = 600.0
_cache: dict[tuple, tuple[float, object]] = {}


def _remember(key: tuple, value):
    if len(_cache) > 128:
        _cache.clear()
    _cache[key] = (time.monotonic() + _CACHE_SECONDS, value)
    return value


def _recall(key: tuple):
    hit = _cache.get(key)
    if hit is None or hit[0] <= time.monotonic():
        return None
    value = hit[1]
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return [dict(item) if isinstance(item, dict) else item for item in value]
    return value


def _offline() -> bool:
    return os.getenv("FITSCREEN_FAKE_EMBEDDINGS", "").lower() in {"1", "true", "yes"}


def lookup(login: str) -> dict | None:
    """Return account facts, {ok: False} if GitHub says 404, or None if the lookup could not run."""
    name = _clean_login(login)
    if not name:
        return None
    if _offline():
        return None
    key = ("user", name.casefold())
    cached = _recall(key)
    if cached is not None:
        return cached
    try:
        response = httpx.get(
            f"https://api.github.com/users/{name}",
            headers=_HEADERS,
            timeout=8,
        )
    except Exception:
        return None
    if response.status_code == 404:
        return _remember(key, {"ok": False, "login": name})
    if response.status_code != 200:
        return None
    body = response.json()
    return _remember(
        key,
        {
            "ok": True,
            "login": body.get("login") or name,
            "html_url": body.get("html_url") or f"https://github.com/{name}",
            "name": body.get("name") or "",
            "bio": (body.get("bio") or "")[:200],
            "public_repos": body.get("public_repos"),
        },
    )


def inspect(login: str) -> dict | None:
    """Account plus recent public repos and languages. None if the lookup could not run."""
    account = lookup(login)
    if not account or not account.get("ok"):
        return account
    repos = _list_repos(account["login"])
    languages = []
    seen: set[str] = set()
    last_activity = ""
    for repo in repos:
        lang = (repo.get("language") or "").strip()
        if lang and lang.casefold() not in seen:
            seen.add(lang.casefold())
            languages.append(lang)
        pushed = repo.get("pushed_at") or ""
        if pushed and pushed > last_activity:
            last_activity = pushed
    return {**account, "repos": repos, "languages": languages, "last_activity": last_activity}


def _clean_login(login: str) -> str:
    name = (login or "").strip().strip("/")
    if not name or not _LOGIN.fullmatch(name):
        return ""
    return name


def _list_repos(login: str) -> list[dict]:
    if _offline() or not login:
        return []
    key = ("repos", login.casefold())
    cached = _recall(key)
    if cached is not None:
        return cached
    try:
        response = httpx.get(
            f"https://api.github.com/users/{login}/repos",
            params={"sort": "updated", "per_page": 10, "type": "owner"},
            headers=_HEADERS,
            timeout=8,
        )
    except Exception:
        return []
    if response.status_code != 200:
        return []
    body = response.json()
    if not isinstance(body, list):
        return []
    out = []
    for row in body:
        if not isinstance(row, dict) or row.get("fork"):
            continue
        out.append(
            {
                "name": row.get("name") or "",
                "html_url": row.get("html_url") or "",
                "language": row.get("language") or "",
                "description": (row.get("description") or "")[:120],
                "pushed_at": (row.get("pushed_at") or "")[:10],
            }
        )
        if len(out) >= 6:
            break
    return _remember(key, out)
