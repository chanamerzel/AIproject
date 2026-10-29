from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from app import google_auth
from app.commands.identity import register_user, sign_in_with_google
from app.queries.identity import get_user_by_email
from app.security import DOORS, STAFF_ROLES, door_mismatch

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _start_session(user_id: str):
    session.pop("google_door", None)
    session.pop("google_role", None)
    session["user_id"] = user_id


def _register(door: str):
    template = "auth/register.html"
    if request.method == "POST":
        role = "candidate"
        if door == "staff":
            role = request.form.get("role", "")
            if role not in STAFF_ROLES:
                flash("יש לבחור תפקיד: מגייסת או מנהל גיוס", "danger")
                return render_template(template, door=door)
        try:
            user_id = register_user(
                request.form.get("email", ""),
                request.form.get("password", ""),
                request.form.get("full_name", ""),
                role,
            )
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template(template, door=door)
        _start_session(user_id)
        return redirect(url_for("main.index"))
    return render_template(template, door=door)


def _login(door: str):
    template = "auth/login.html"
    if request.method == "POST":
        user = get_user_by_email(request.form.get("email", ""))
        if not user or not check_password_hash(user["password_hash"], request.form.get("password", "")):
            flash("אימייל או סיסמה שגויים", "danger")
            return render_template(template, door=door)
        problem = door_mismatch(user["role"], door)
        if problem:
            flash(problem, "warning")
            return render_template(template, door=door)
        _start_session(user["id"])
        return redirect(url_for("main.index"))
    return render_template(template, door=door)


@bp.route("/register", methods=["GET", "POST"])
def register():
    return _register("candidate")


@bp.route("/login", methods=["GET", "POST"])
def login():
    return _login("candidate")


@bp.route("/recruit/register", methods=["GET", "POST"])
def recruit_register():
    return _register("staff")


@bp.route("/recruit/login", methods=["GET", "POST"])
def recruit_login():
    return _login("staff")


@bp.route("/google")
def google_start():
    if not google_auth.google_enabled():
        abort(404)
    door = request.args.get("door", "candidate")
    if door not in DOORS:
        abort(400)
    session["google_door"] = door
    role = request.args.get("role", "")
    session["google_role"] = role if door == "staff" and role in STAFF_ROLES else None
    return google_auth.start_login(url_for("auth.google_callback", _external=True))


@bp.route("/google/callback")
def google_callback():
    if not google_auth.google_enabled():
        abort(404)
    door = session.get("google_door") or "candidate"
    fallback = url_for("auth.recruit_login" if door == "staff" else "auth.login")
    try:
        identity = google_auth.finish_login()
    except Exception:
        current_app.logger.exception("Google sign-in failed")
        flash("הכניסה עם Google לא הושלמה. אפשר לנסות שוב.", "danger")
        return redirect(fallback)
    try:
        user_id = sign_in_with_google(
            identity["email"],
            identity["name"],
            identity["email_verified"],
            door,
            session.get("google_role"),
        )
    except ValueError as exc:
        flash(str(exc), "warning")
        return redirect(fallback)
    _start_session(user_id)
    return redirect(url_for("main.index"))


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.index"))
