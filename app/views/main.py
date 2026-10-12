from flask import Blueprint, jsonify, redirect, render_template, url_for

from app import db
from app.security import current_user

bp = Blueprint("main", __name__)


@bp.route("/health")
def health():
    from agent.rag import embedding_mode

    body = {
        "database": {"backend": db.backend_name(), "target": db.describe_target()},
        "embeddings": embedding_mode(),
    }
    try:
        body["database"]["counts"] = db.ping()
        body["status"] = "ok"
        return jsonify(body), 200
    except Exception as exc:
        body["status"] = "error"
        body["database"]["error"] = str(exc)
        return jsonify(body), 503


@bp.route("/")
def index():
    user = current_user()
    if not user:
        return render_template("landing.html")
    if user["role"] in ("hr", "hiring_manager"):
        return redirect(url_for("dashboard.index"))
    return redirect(url_for("jobs.table"))


@bp.app_context_processor
def inject_user():
    return {"current_user": current_user()}
