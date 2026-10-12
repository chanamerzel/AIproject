from functools import wraps

from flask import abort, redirect, session, url_for

from app.queries.identity import get_user


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return get_user(user_id)


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
                return redirect(url_for("auth.login"))
            if user["role"] not in roles:
                abort(403)
            return fn(*args, **kwargs)

        return wrapper

    return decorator
