from flask import Blueprint, render_template

from app.queries.jobs import application_status_counts, dashboard_rows
from app.security import role_required

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@bp.route("/")
@role_required("hr", "hiring_manager")
def index():
    jobs = dashboard_rows()
    counts = application_status_counts()
    return render_template("dashboard/index.html", jobs=jobs, counts=counts)
