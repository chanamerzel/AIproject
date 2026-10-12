"""Create demo users and jobs through commands (so every row has events). Safe to run repeatedly."""

from pathlib import Path

from app import create_app
from app.commands.identity import register_user
from app.commands.jobs import draft_job, open_job
from app.queries.identity import get_user_by_email
from app.queries.jobs import list_jobs

USERS = [
    ("hr@fit.local", "secret1", "Noa HR", "hr"),
    ("hm@fit.local", "secret1", "Gil Manager", "hiring_manager"),
    ("cand@fit.local", "secret1", "Dana Candidate", "candidate"),
    ("cand2@fit.local", "secret1", "Yossi Candidate", "candidate"),
]

JOBS = [
    {
        "title": "Python Backend",
        "description": "Build Flask services, SQL projections, and tests for our hiring platform.",
        "must": "Python, Flask, SQL",
        "nice": "Docker, RAG",
        "years": 3,
        "location": "Tel Aviv",
        "open": True,
    },
    {
        "title": "Data Engineer",
        "description": "Own batch and streaming pipelines, data modelling and warehouse quality.",
        "must": "Python, SQL, Airflow",
        "nice": "Spark, dbt",
        "years": 2,
        "location": "Haifa (hybrid)",
        "open": True,
    },
    {
        "title": "Frontend Developer",
        "description": "Build accessible recruiter dashboards with modern JavaScript.",
        "must": "JavaScript, React, CSS",
        "nice": "TypeScript, Chart.js",
        "years": 2,
        "location": "Remote",
        "open": False,
    },
]


def main():
    app = create_app()
    with app.app_context():
        ids = {}
        for email, password, name, role in USERS:
            existing = get_user_by_email(email)
            ids[email] = existing["id"] if existing else register_user(email, password, name, role)

        existing_titles = {j["title"] for j in list_jobs()}
        for job in JOBS:
            if job["title"] in existing_titles:
                continue
            job_id = draft_job(
                ids["hr@fit.local"], job["title"], job["description"], job["must"], job["nice"], job["years"], job["location"]
            )
            if job["open"]:
                open_job(job_id, ids["hm@fit.local"])

        print("Demo users (password secret1): " + ", ".join(u[0] for u in USERS))
        for job in list_jobs():
            print(f"  {job['status']:<6} {job['title']}  ({job['id']})")
        print("Sample CVs:", Path("samples").resolve())


if __name__ == "__main__":
    main()
