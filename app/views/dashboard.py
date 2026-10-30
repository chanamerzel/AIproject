from flask import Blueprint, render_template

from app.queries.jobs import application_status_counts, dashboard_rows, list_jobs
from app.security import current_user, role_required

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@bp.route("/")
@role_required("hr", "hiring_manager")
def index():
    jobs = dashboard_rows()
    counts = application_status_counts()
    pending_jobs = []
    if current_user()["role"] == "hiring_manager":
        pending_jobs = list_jobs(status="Draft")
    return render_template(
        "dashboard/index.html",
        jobs=jobs,
        counts=counts,
        pending_jobs=pending_jobs,
    )
