import json
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from app.commands.applications import RESCREENABLE, decide, request_rescreen, submit_application
from app.cv_text import extract_text
from app.event_store import EventStore
from app.queries.applications import get_application, list_for_candidate, screening_history
from app.queries.notifications import decision_emails
from app.security import current_user, login_required, role_required

bp = Blueprint("applications", __name__, url_prefix="/applications")


@bp.route("/mine")
@role_required("candidate")
def mine():
    rows = list_for_candidate(current_user()["id"])
    return render_template("applications/mine.html", applications=rows)


@bp.route("/apply/<job_id>", methods=["POST"])
@role_required("candidate")
def apply(job_id):
    file = request.files.get("cv")
    if not file or not file.filename:
        flash("יש לצרף קובץ קורות חיים", "danger")
        return redirect(url_for("jobs.detail", job_id=job_id))
    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".txt", ".pdf", ".md"}:
        flash("אפשר להעלות קובץ TXT, MD או PDF עם טקסט.", "danger")
        return redirect(url_for("jobs.detail", job_id=job_id))
    text, data = extract_text(file)
    if len(text) < 40:
        flash("לא הצלחנו לקרוא מספיק טקסט מהקובץ. אפשר לנסות TXT או PDF עם טקסט.", "danger")
        return redirect(url_for("jobs.detail", job_id=job_id))
    safe_name = secure_filename(file.filename) or f"cv{suffix}"
    dest = Path(current_app.config["UPLOAD_FOLDER"]) / f"{uuid4().hex}_{safe_name}"
    dest.write_bytes(data)
    try:
        application_id = submit_application(job_id, current_user()["id"], str(dest), text)
    except ValueError as exc:
        dest.unlink(missing_ok=True)
        flash(str(exc), "danger")
        return redirect(url_for("jobs.detail", job_id=job_id))
    try:
        from agent.rag import embed_application

        embed_application(application_id, job_id, text)
    except Exception:
        current_app.logger.exception("CV embedding failed")
        flash("המועמדות נשמרה, אך ההטמעה הווקטורית נכשלה. הסוכן עדיין מעריך לפי טקסט.", "warning")
    flash("המועמדות נקלטה. צוות הגיוס יקבל הערכה מהסוכן ברקע.", "success")
    return redirect(url_for("applications.detail", application_id=application_id))


@bp.route("/<application_id>")
@login_required
def detail(application_id):
    row = get_application(application_id)
    if not row:
        flash("מועמדות לא נמצאה", "danger")
        return redirect(url_for("main.index"))
    user = current_user()
    if user["role"] == "candidate" and row["candidate_id"] != user["id"]:
        flash("אין גישה למועמדות זו", "danger")
        return redirect(url_for("applications.mine"))
    is_staff = user["role"] in ("hr", "hiring_manager")
    report = json.loads(row["agent_report_json"]) if is_staff and row.get("agent_report_json") else None
    if report:
        from agent.deep_agent import state_for_saved_report
        from app.cv_text import enrich_stored_text

        report = state_for_saved_report(
            report,
            enrich_stored_text(row.get("cv_text") or "", row.get("cv_path")),
            row.get("must_have_skills") or "",
            row.get("nice_to_have_skills") or "",
            row.get("candidate_name") or "",
        )
    timeline = EventStore.for_aggregate(application_id)
    failures = [e for e in timeline if e["event_type"] == "ApplicationScreeningFailed"]
    last_failure = failures[-1]["payload"].get("error") if is_staff and failures else None
    return render_template(
        "applications/detail.html",
        application=row,
        report=report,
        timeline=timeline,
        last_failure=last_failure,
        history=screening_history(application_id, timeline) if is_staff else [],
        emails=decision_emails(application_id, timeline) if is_staff else [],
        can_rescreen=user["role"] == "hr" and row["status"] in RESCREENABLE,
    )


@bp.route("/<application_id>/rescreen", methods=["POST"])
@role_required("hr")
def rescreen_route(application_id):
    try:
        request_rescreen(application_id, request.form.get("reason", ""), current_user()["id"])
        flash("הבקשה נשמרה כאירוע. הסוכן יעריך את המועמדות מחדש בסבב הקרוב.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("applications.detail", application_id=application_id))


@bp.route("/<application_id>/decide", methods=["POST"])
@role_required("hr")
def decide_route(application_id):
    decision = request.form.get("decision", "")
    reason = request.form.get("reason", "").strip()
    try:
        decide(application_id, decision, reason, current_user()["id"])
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("applications.detail", application_id=application_id))
    flash("ההחלטה נשמרה.", "success")
    return redirect(url_for("applications.detail", application_id=application_id))
