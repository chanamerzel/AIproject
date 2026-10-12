from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from app.commands.identity import register_user
from app.queries.identity import get_user_by_email

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        try:
            user_id = register_user(
                request.form["email"],
                request.form["password"],
                request.form["full_name"],
                request.form["role"],
            )
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template("auth/register.html")
        session["user_id"] = user_id
        return redirect(url_for("main.index"))
    return render_template("auth/register.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = get_user_by_email(request.form["email"])
        if not user or not check_password_hash(user["password_hash"], request.form["password"]):
            flash("אימייל או סיסמה שגויים", "danger")
            return render_template("auth/login.html")
        session["user_id"] = user["id"]
        return redirect(url_for("main.index"))
    return render_template("auth/login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
