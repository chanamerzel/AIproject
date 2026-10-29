import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, g, render_template, request

from app.csrf import csrf_token, protect
from app.db import bind, init_db, release
from app.labels import (
    DECISION_LABELS,
    EVENT_LABELS,
    GITHUB_LABELS,
    LINKEDIN_LABELS,
    RECOMMENDATION_LABELS,
    ROLE_LABELS,
    STATUS_BADGE,
    STATUS_LABELS,
)


_JERUSALEM = ZoneInfo("Asia/Jerusalem")


def create_app(test_config=None):
    app = Flask(__name__)
    root = Path(__file__).resolve().parent.parent
    app.config["SECRET_KEY"] = "dev-secret"
    app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    app.config["DATABASE_URL"] = f"sqlite:///{root / 'fitscreen.db'}"
    app.config["UPLOAD_FOLDER"] = str(root / "uploads")
    app.config["AGENT_API_KEY"] = "dev-agent-key"
    app.config["CHROMA_PATH"] = str(root / "chroma_data")

    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env")
        for key, env in (
            ("SECRET_KEY", "FLASK_SECRET_KEY"),
            ("DATABASE_URL", "DATABASE_URL"),
            ("AGENT_API_KEY", "AGENT_API_KEY"),
            ("CHROMA_PATH", "CHROMA_PATH"),
            ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_ID"),
            ("GOOGLE_CLIENT_SECRET", "GOOGLE_CLIENT_SECRET"),
        ):
            value = os.getenv(env, "").strip()
            if value:
                app.config[key] = value
    except Exception:
        pass

    if test_config:
        app.config.update(test_config)

    if not app.config.get("TESTING") and app.config["SECRET_KEY"] in {"dev-secret", "change-me"}:
        app.logger.warning("FLASK_SECRET_KEY is still the default. Set a private value in .env.")

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["CHROMA_PATH"]).mkdir(parents=True, exist_ok=True)
    init_db(app.config["DATABASE_URL"])

    from app.google_auth import google_enabled, init_google

    init_google(app)

    from app.views.auth import bp as auth_bp
    from app.views.jobs import bp as jobs_bp
    from app.views.applications import bp as apps_bp
    from app.views.dashboard import bp as dash_bp
    from app.views.internal import bp as internal_bp
    from app.views.main import bp as main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(apps_bp)
    app.register_blueprint(dash_bp)
    app.register_blueprint(internal_bp)

    app.before_request(bind)
    app.before_request(protect)

    @app.before_request
    def _mark_request():
        g.started = time.perf_counter()

    @app.teardown_request
    def _release_and_log(exc):
        started = getattr(g, "started", None)
        release()
        if started is None:
            return
        elapsed_ms = (time.perf_counter() - started) * 1000
        if elapsed_ms >= 800 and request.path != "/health":
            logging.getLogger("fitscreen.web").info(
                "slow %s %s %.0fms", request.method, request.path, elapsed_ms
            )

    @app.template_filter("local_time")
    def local_time(value):
        if not value:
            return ""
        text = str(value).replace("Z", "+00:00")
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            return value
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(_JERUSALEM).strftime("%d/%m/%Y %H:%M")

    @app.context_processor
    def inject_labels():
        return {
            "ROLE_LABELS": ROLE_LABELS,
            "STATUS_LABELS": STATUS_LABELS,
            "STATUS_BADGE": STATUS_BADGE,
            "RECOMMENDATION_LABELS": RECOMMENDATION_LABELS,
            "DECISION_LABELS": DECISION_LABELS,
            "EVENT_LABELS": EVENT_LABELS,
            "GITHUB_LABELS": GITHUB_LABELS,
            "LINKEDIN_LABELS": LINKEDIN_LABELS,
            "csrf_token": csrf_token,
            "google_enabled": google_enabled(app),
        }

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def too_large(_e):
        return render_template("errors/413.html"), 413

    return app
