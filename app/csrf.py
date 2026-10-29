import secrets

from flask import abort, current_app, request, session


def csrf_token() -> str:
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def protect():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    if current_app.config.get("TESTING"):
        return
    if request.path.startswith("/internal"):
        return
    sent = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
    if not sent or sent != session.get("_csrf"):
        abort(400)
