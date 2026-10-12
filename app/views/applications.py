import json
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from app.commands.applications import decide, record_email_sent, submit_application
from app.cv_text import extract_text
from app.event_store import EventStore
from app.queries.applications import get_application, list_for_candidate
from app.queries.identity import get_user
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
    text, data = extract_text(file)
    if len(text) < 40:
        flash("לא הצלחנו לקרוא מספיק טקסט מקורות החיים. נסי קובץ TXT או PDF עם טקסט.", "danger")
        return redirect(url_for("jobs.detail", job_id=job_id))
    dest = Path(current_app.config["UPLOAD_FOLDER"]) / f"{uuid4()}_{file.filename}"
    dest.write_bytes(data)
    try:
        application_id = submit_application(job_id, current_user()["id"], str(dest), text)
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("jobs.detail", job_id=job_id))
    try:
        from agent.rag import embed_application

        embed_application(application_id, job_id, text)
    except Exception:
        current_app.logger.exception("CV embedding failed")
        flash("המועמדות נשמרה, אך ההטמעה הווקטורית נכשלה. הסוכן עדיין מעריך לפי טקסט.", "warning")
    flash("המועמדות נקלטה. סוכן ההערכה רץ בתהליך נפרד: python -m agent.worker", "success")
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
    timeline = EventStore.for_aggregate(application_id)
    failures = [e for e in timeline if e["event_type"] == "ApplicationScreeningFailed"]
    last_failure = failures[-1]["payload"].get("error") if is_staff and failures else None
    return render_template(
        "applications/detail.html",
        application=row,
        report=report,
        timeline=timeline,
        last_failure=last_failure,
    )


@bp.route("/<application_id>/decide", methods=["POST"])
@role_required("hr", "hiring_manager")
def decide_route(application_id):
    decision = request.form["decision"]
    reason = request.form.get("reason", "").strip()
    try:
        decide(application_id, decision, reason, current_user()["id"])
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("applications.detail", application_id=application_id))
    row = get_application(application_id)
    candidate = get_user(row["candidate_id"])
    subject = {
        "interview": f"הזמנה לראיון — {row['job_title']}",
        "reject": f"עדכון לגבי המועמדות — {row['job_title']}",
        "offer": f"הצעת עבודה — {row['job_title']}",
    }[decision]
    from agent.tools_bridge import send_decision_email

    send_decision_email(candidate["email"], subject, reason or subject)
    record_email_sent(application_id, candidate["email"], subject)
    flash("ההחלטה נשמרה כאירוע. מייל נשלח או נרשם בלוג אם Gmail MCP כבוי.", "success")
    return redirect(url_for("applications.detail", application_id=application_id))
