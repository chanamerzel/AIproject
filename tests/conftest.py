import os

import pytest

# Offline, deterministic test run: hash embeddings, LLM-free agent pipeline, no web calls.
# Set before the app loads .env, because load_dotenv never overrides existing variables.
os.environ["FITSCREEN_FAKE_EMBEDDINGS"] = "1"
os.environ["FITSCREEN_AGENT_MODE"] = "pipeline"
os.environ["TAVILY_API_KEY"] = ""
os.environ["DATABASE_URL"] = ""
os.environ["LLM_PROVIDER"] = "auto"
os.environ["GEMINI_API_KEY"] = ""
os.environ["GOOGLE_API_KEY"] = ""
os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["GOOGLE_CLIENT_SECRET"] = ""
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:9"

from app import create_app  # noqa: E402


# TEST_DATABASE_URL=mssql+pymssql://... runs the whole suite against SQL Server (the Somee engine).
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()


@pytest.fixture()
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test",
            "DATABASE_URL": TEST_DATABASE_URL or f"sqlite:///{tmp_path / 't.db'}",
            "UPLOAD_FOLDER": str(tmp_path / "uploads"),
            "CHROMA_PATH": str(tmp_path / "chroma"),
            "AGENT_API_KEY": "test-key",
        }
    )
    if TEST_DATABASE_URL:
        from app import db

        for table in ("events", "applications", "jobs", "users"):
            db.execute(f"DELETE FROM {table}")
    return application


@pytest.fixture()
def client(app):
    return app.test_client()


def register(client, email, role, name=None):
    full_name = name or email.split("@")[0]
    if role != "candidate":
        with client.application.app_context():
            from app.commands.identity import register_user

            register_user(email, "secret1", full_name, role)
        return login(client, email)
    return client.post(
        "/auth/register",
        data={
            "email": email,
            "password": "secret1",
            "full_name": full_name,
        },
        follow_redirects=True,
    )


def logout(client):
    return client.get("/auth/logout", follow_redirects=True)


def login(client, email):
    with client.application.app_context():
        from app.queries.identity import get_user_by_email

        user = get_user_by_email(email)
    staff = user is not None and user["role"] != "candidate"
    return client.post(
        "/auth/recruit/login" if staff else "/auth/login",
        data={"email": email, "password": "secret1"},
        follow_redirects=True,
    )


def open_python_job(client):
    """HR drafts the job; the hiring manager approves it, as in the product."""
    register(client, "hr@x.test", "hr", "HR User")
    job_page = client.post(
        "/jobs/new",
        data={
            "title": "Python Backend",
            "description": "Build Flask services with SQL and pytest.",
            "must_have_skills": "Python, Flask, SQL",
            "nice_to_have_skills": "Docker",
            "min_years": "3",
            "location": "Tel Aviv",
        },
        follow_redirects=True,
    )
    job_id = job_page.request.path.split("/")[-1]
    logout(client)
    with client.application.app_context():
        from app.queries.identity import get_user_by_email

        has_manager = get_user_by_email("hm@x.test") is not None
    if has_manager:
        login(client, "hm@x.test")
    else:
        register(client, "hm@x.test", "hiring_manager", "Hiring Manager")
    client.post(f"/jobs/{job_id}/open", follow_redirects=True)
    logout(client)
    return job_id
