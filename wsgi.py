import atexit
import logging
import os
import subprocess
import sys
from pathlib import Path

from app import create_app

app = create_app()
_worker: subprocess.Popen | None = None


def should_start_worker(environ=None, *, reloader_enabled: bool = True) -> bool:
    """Start one worker in the process that actually serves pages."""
    env = os.environ if environ is None else environ
    flag = env.get("FITSCREEN_DISABLE_WORKER", "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return False
    if env.get("WERKZEUG_RUN_MAIN") == "true":
        return True
    return not reloader_enabled


def start_worker() -> subprocess.Popen:
    """Separate process, same as `python -m agent.worker`. Screening never runs inside a request."""
    global _worker
    if _worker is not None and _worker.poll() is None:
        return _worker
    root = Path(__file__).resolve().parent
    _worker = subprocess.Popen([sys.executable, "-m", "agent.worker"], cwd=str(root))
    atexit.register(_stop_worker)
    logging.getLogger("fitscreen.web").info("screening worker started pid=%s", _worker.pid)
    return _worker


def _stop_worker() -> None:
    if _worker is not None and _worker.poll() is None:
        _worker.terminate()


if __name__ == "__main__":
    # The reloader restarts the site on every save and kills a screening halfway through.
    reloader = False
    if should_start_worker(reloader_enabled=reloader):
        start_worker()
    port = int(os.environ.get("WEB_PORT") or "5000")
    app.run(debug=True, use_reloader=reloader, host="127.0.0.1", port=port)
