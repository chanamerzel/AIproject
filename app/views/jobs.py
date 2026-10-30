from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.commands.jobs import close_job, draft_job, open_job
from app.queries.applications import get_application_by_candidate_job, list_for_job
from app.queries.jobs import count_jobs, get_job, list_jobs
from app.queries.ranking import ranking_for_job
from app.queries.semantic import similar_candidates_for_job
from app.security import current_user, login_required, role_required

bp = Blueprint("jobs", __name__, url_prefix="/jobs")

JOBS_PAGE_SIZE = 6


def _page_number():
    raw = request.args.get("page", "1")
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 1


@bp.route("/")
@login_required
def table():
    q = request.args.get("q", "").strip()
    page = _page_number()
    total = count_jobs(status="Open", q=q or None)
    pages = max(1, (total + JOBS_PAGE_SIZE - 1) // JOBS_PAGE_SIZE) if total else 1
    if page > pages:
        page = pages
    jobs = []
    if total:
        jobs = list_jobs(
            status="Open",
            q=q or None,
            limit=JOBS_PAGE_SIZE,
            offset=(page - 1) * JOBS_PAGE_SIZE,
        )
    pager_args = {"q": q} if q else {}
    pending_jobs = []
    if current_user()["role"] == "hiring_manager":
        pending_jobs = list_jobs(status="Draft", q=q or None)
    return render_template(
        "jobs/table.html",
        jobs=jobs,
        pending_jobs=pending_jobs,
        q=q,
        page=page,
        pages=pages,
        open_count=total,
        prev_url=url_for("jobs.table", page=page - 1, **pager_args) if page > 1 else None,
        next_url=url_for("jobs.table", page=page + 1, **pager_args) if page < pages else None,
        page_links=[
            {
                "n": n,
                "url": url_for("jobs.table", page=n, **pager_args),
                "current": n == page,
            }
            for n in range(1, pages + 1)
        ],
    )


@bp.route("/new", methods=["GET", "POST"])
@role_required("hr")
def create():
    if request.method == "POST":
        try:
            job_id = draft_job(
                current_user()["id"],
                request.form["title"],
                request.form["description"],
                request.form["must_have_skills"],
                request.form.get("nice_to_have_skills", ""),
                request.form.get("min_years", 0),
                request.form["location"],
            )
        except ValueError as exc:
            flash(str(exc), "danger")
            return render_template("jobs/form.html")
        flash("המשרה נשמרה כטיוטה. מנהל הגיוס יאשר את פתיחתה לקבלת מועמדויות.", "success")
        return redirect(url_for("jobs.detail", job_id=job_id))
    return render_template("jobs/form.html")


@bp.route("/<job_id>")
@login_required
def detail(job_id):
    job = get_job(job_id)
    if not job:
        flash("משרה לא נמצאה", "danger")
        return redirect(url_for("jobs.table"))
    user = current_user()
    if user["role"] == "candidate" and job["status"] != "Open":
        abort(404)
    applications = []
    my_application = None
    if user["role"] in ("hr", "hiring_manager"):
        applications = list_for_job(job_id, request.args.get("app_status") or None, shape="summary")
    else:
        my_application = get_application_by_candidate_job(user["id"], job_id)
    return render_template(
        "jobs/detail.html",
        job=job,
        applications=applications,
        my_application=my_application,
    )


@bp.route("/<job_id>/open", methods=["POST"])
@role_required("hiring_manager")
def open_route(job_id):
    try:
        open_job(job_id, current_user()["id"])
        flash("המשרה פתוחה לקבלת מועמדויות", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("jobs.detail", job_id=job_id))


@bp.route("/<job_id>/close", methods=["POST"])
@role_required("hiring_manager")
def close_route(job_id):
    close_job(job_id, current_user()["id"])
    flash("המשרה נסגרה", "success")
    return redirect(url_for("jobs.detail", job_id=job_id))


@bp.route("/<job_id>/ranking")
@role_required("hr", "hiring_manager")
def ranking(job_id):
    job = get_job(job_id)
    if not job:
        return redirect(url_for("jobs.table"))
    return render_template("jobs/ranking.html", job=job, ranking=ranking_for_job(job))


@bp.route("/<job_id>/semantic")
@role_required("hr", "hiring_manager")
def semantic(job_id):
    job = get_job(job_id)
    if not job:
        return redirect(url_for("jobs.table"))
    matches = similar_candidates_for_job(job)
    return render_template("jobs/semantic.html", job=job, matches=matches)
