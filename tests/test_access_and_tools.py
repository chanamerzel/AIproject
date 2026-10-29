from io import BytesIO
from pathlib import Path

from app.commands.applications import complete_screening, decide, start_screening
from app.queries.applications import get_application, list_for_job
from app.queries.identity import get_user_by_email
from mcp_studio.evaluate_requirement_coverage import evaluate_requirement_coverage
from mcp_studio.extract_resume_profile import extract_resume_profile
from tests.conftest import logout, open_python_job, register


def test_public_register_cannot_choose_staff_role(app, client):
    client.post(
        "/auth/register",
        data={
            "email": "sneak@x.test",
            "password": "secret1",
            "full_name": "Sneak",
            "role": "hr",
        },
        follow_redirects=True,
    )
    with app.app_context():
        assert get_user_by_email("sneak@x.test")["role"] == "candidate"


def test_candidate_cannot_see_draft_jobs(client):
    register(client, "hr@x.test", "hr", "HR User")
    page = client.post(
        "/jobs/new",
        data={
            "title": "Secret Draft",
            "description": "Internal only",
            "must_have_skills": "Python",
            "nice_to_have_skills": "",
            "min_years": "0",
            "location": "Haifa",
        },
        follow_redirects=True,
    )
    job_id = page.request.path.split("/")[-1]
    logout(client)
    register(client, "c@x.test", "candidate", "Cand")
    listing = client.get("/jobs/?status=Draft")
    assert "Secret Draft" not in listing.get_data(as_text=True)
    hidden = client.get(f"/jobs/{job_id}")
    assert hidden.status_code == 404


def test_skill_match_is_a_whole_word():
    java = evaluate_requirement_coverage("Java", "", "Built services in JavaScript and PostgreSQL")
    assert java["must_have_matched"] == []
    assert java["must_have_missing"] == ["Java"]
    real = evaluate_requirement_coverage("Java, SQL", "", "Java and SQL on the backend. No JavaScript.")
    assert real["must_have_matched"] == ["Java", "SQL"]
    java_quote = next(item for item in real["skill_evidence"] if item["skill"] == "Java")
    assert java_quote["matched"] is True
    assert "Java and SQL" in java_quote["quote"]
    assert java["skill_evidence"][0]["quote"] is None


def test_profile_extracts_employer_and_github():
    profile = extract_resume_profile(
        "Dana\n5 years at NovaLabs.\nGitHub: https://github.com/pallets/flask\nעבדה בחברת אלפא.\n"
    )
    assert profile["last_company"] == "NovaLabs"
    assert profile["github_login"] == "pallets"
    assert profile["github_url"] == "https://github.com/pallets/flask"
    assert extract_resume_profile("that format is not a company")["last_company"] is None


def test_interview_reason_is_stored(app, client):
    job_id = open_python_job(client)
    cv = Path("samples/cv_python.txt")
    register(client, "dana@x.test", "candidate", "Dana")
    client.post(
        f"/applications/apply/{job_id}",
        data={"cv": (BytesIO(cv.read_bytes()), cv.name)},
        follow_redirects=True,
    )
    with app.app_context():
        row = list_for_job(job_id)[0]
        start_screening(row["id"])
        complete_screening(
            row["id"],
            {"overall_score": 80, "skill_coverage": 80, "semantic_fit": 80, "recommendation": "advance"},
        )
        decide(row["id"], "interview", "מתאימה לראיון טכני", "hr-actor")
        saved = get_application(row["id"])
    assert saved["status"] == "Interview"
    assert saved["decision_reason"] == "מתאימה לראיון טכני"


def test_decision_without_choice_is_rejected(app, client):
    job_id = open_python_job(client)
    cv = Path("samples/cv_python.txt")
    register(client, "dana2@x.test", "candidate", "Dana")
    client.post(
        f"/applications/apply/{job_id}",
        data={"cv": (BytesIO(cv.read_bytes()), cv.name)},
        follow_redirects=True,
    )
    with app.app_context():
        row = list_for_job(job_id)[0]
        start_screening(row["id"])
        complete_screening(
            row["id"],
            {"overall_score": 80, "skill_coverage": 80, "semantic_fit": 80, "recommendation": "advance"},
        )
        try:
            decide(row["id"], "", "סתם שמירה", "hr-actor")
            raised = False
        except ValueError as exc:
            raised = True
            assert "לבחור" in str(exc)
        assert raised
        assert get_application(row["id"])["status"] == "Screened"
