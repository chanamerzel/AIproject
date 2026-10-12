import os
from pathlib import Path

from flask import Flask, render_template

from app.db import init_db
from app.labels import DECISION_LABELS, RECOMMENDATION_LABELS, ROLE_LABELS, STATUS_BADGE, STATUS_LABELS


def create_app(test_config=None):
    app = Flask(__name__)
    root = Path(__file__).resolve().parent.parent
    app.config["SECRET_KEY"] = "dev-secret"
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
        ):
            value = os.getenv(env, "").strip()
            if value:
                app.config[key] = value
    except Exception:
        pass

    if test_config:
        app.config.update(test_config)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["CHROMA_PATH"]).mkdir(parents=True, exist_ok=True)
    init_db(app.config["DATABASE_URL"])

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

    @app.context_processor
    def inject_labels():
        return {
            "ROLE_LABELS": ROLE_LABELS,
            "STATUS_LABELS": STATUS_LABELS,
            "STATUS_BADGE": STATUS_BADGE,
            "RECOMMENDATION_LABELS": RECOMMENDATION_LABELS,
            "DECISION_LABELS": DECISION_LABELS,
        }

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errors/403.html"), 403

    return app
