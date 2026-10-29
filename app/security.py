from functools import wraps

from flask import abort, g, redirect, session, url_for

from app.queries.identity import get_user

STAFF_ROLES = ("hr", "hiring_manager")
DOORS = ("candidate", "staff")


def door_mismatch(role: str, door: str) -> str | None:
    """Why this account cannot enter through this door, or None."""
    if door == "staff" and role not in STAFF_ROLES:
        return "זה חשבון מועמד. הכניסה שלך היא בדלת המועמדים."
    if door == "candidate" and role in STAFF_ROLES:
        return "זה חשבון של צוות גיוס. הכניסה שלך היא בדלת המגייסים."
    return None


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    if getattr(g, "user_cache_id", None) == user_id:
        return g.user_cache
    user = get_user(user_id)
    g.user_cache_id = user_id
    g.user_cache = user
    return user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("auth.login"))
        return fn(*args, **kwargs)

    return wrapper


def role_required(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user:
                staff_only = all(role in STAFF_ROLES for role in roles)
                return redirect(url_for("auth.recruit_login" if staff_only else "auth.login"))
            if user["role"] not in roles:
                abort(403)
            return fn(*args, **kwargs)

        return wrapper

    return decorator
