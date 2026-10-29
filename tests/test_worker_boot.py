"""The website process starts the screener beside it, and a dropped screening returns to the queue."""

from agent.worker import requeue_abandoned
from app.commands.applications import start_screening, submit_application
from app.commands.identity import register_user
from app.commands.jobs import draft_job, open_job
from app.queries.applications import get_application
from wsgi import should_start_worker


def test_worker_starts_only_in_the_serving_process():
    assert should_start_worker({}) is False
    assert should_start_worker({"WERKZEUG_RUN_MAIN": "true"}) is True
    assert should_start_worker({}, reloader_enabled=False) is True
    assert should_start_worker({"FITSCREEN_DISABLE_WORKER": "1"}, reloader_enabled=False) is False
    assert should_start_worker({"WERKZEUG_RUN_MAIN": "true", "FITSCREEN_DISABLE_WORKER": "1"}) is False


def test_abandoned_screening_returns_to_the_queue(app):
    with app.app_context():
        hr = register_user("hr-boot@x.test", "secret1", "Noa", "hr")
        manager = register_user("hm-boot@x.test", "secret1", "Gil", "hiring_manager")
        candidate = register_user("cand-boot@x.test", "secret1", "Dana", "candidate")
        job_id = draft_job(hr, "Python", "APIs", "Python, Flask", "", 2, "Tel Aviv")
        open_job(job_id, manager)
        application_id = submit_application(job_id, candidate, "cv.txt", "Python and Flask " * 5)
        start_screening(application_id)
        assert get_application(application_id)["status"] == "Screening"
        assert requeue_abandoned(older_than_seconds=0) == 1
        assert get_application(application_id)["status"] == "Submitted"
        start_screening(application_id)
        assert requeue_abandoned(older_than_seconds=600) == 0
        assert get_application(application_id)["status"] == "Screening"
