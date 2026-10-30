from flask import Blueprint, render_template, request, url_for

from app.queries.jobs import application_status_counts, count_jobs, dashboard_rows, list_jobs
from app.security import current_user, role_required

bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")

DASHBOARD_PAGE_SIZE = 6


def _page_number():
    raw = request.args.get("page", "1")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


@bp.route("/")
@role_required("hr", "hiring_manager")
def index():
    page = _page_number()
    open_count = count_jobs(status="Open")
    pages = max(1, (open_count + DASHBOARD_PAGE_SIZE - 1) // DASHBOARD_PAGE_SIZE) if open_count else 1
    if page > pages:
        page = pages
    jobs = []
    if open_count:
        jobs = dashboard_rows(limit=DASHBOARD_PAGE_SIZE, offset=(page - 1) * DASHBOARD_PAGE_SIZE)
    chart_jobs = dashboard_rows() if open_count else []
    counts = application_status_counts()
    pending_jobs = []
    if current_user()["role"] == "hiring_manager":
        pending_jobs = list_jobs(status="Draft")
    return render_template(
        "dashboard/index.html",
        jobs=jobs,
        chart_jobs=chart_jobs,
        open_count=open_count,
        applicant_total=sum(row["applicant_count"] for row in chart_jobs),
        counts=counts,
        pending_jobs=pending_jobs,
        pages=pages,
        prev_url=url_for("dashboard.index", page=page - 1) if page > 1 else None,
        next_url=url_for("dashboard.index", page=page + 1) if page < pages else None,
        page_links=[
            {"n": n, "url": url_for("dashboard.index", page=n), "current": n == page}
            for n in range(1, pages + 1)
        ],
    )
