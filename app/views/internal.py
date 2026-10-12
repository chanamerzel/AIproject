from flask import Blueprint, current_app, jsonify, request

from app.commands.applications import complete_screening, start_screening
from app.queries.applications import get_application, pending_screening

bp = Blueprint("internal", __name__, url_prefix="/internal")


def _authorized():
    key = request.headers.get("X-Agent-Key", "")
    return key and key == current_app.config["AGENT_API_KEY"]


@bp.route("/applications/pending")
def pending():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    return jsonify(pending_screening())


@bp.route("/applications/<application_id>")
def one(application_id):
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    row = get_application(application_id)
    if not row:
        return jsonify({"error": "not found"}), 404
    return jsonify(row)


@bp.route("/commands/start-screening", methods=["POST"])
def start():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    start_screening(request.json["application_id"])
    return jsonify({"ok": True})


@bp.route("/commands/complete-screening", methods=["POST"])
def complete():
    if not _authorized():
        return jsonify({"error": "unauthorized"}), 401
    body = request.json
    complete_screening(body["application_id"], body["report"])
    return jsonify({"ok": True})
