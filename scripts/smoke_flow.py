"""End-to-end smoke test against a running FitScreen (default http://127.0.0.1:5000).

Logs in as the seeded candidate, applies to "Python Backend" with samples/cv_python.txt,
then logs in as HR and prints what the application page shows.

Usage:  python -m scripts.smoke_flow [base_url]
"""

import re
import sys
from pathlib import Path

import httpx


def login(client: httpx.Client, email: str) -> None:
    client.get("/auth/logout")
    r = client.post("/auth/login", data={"email": email, "password": "secret1"})
    if r.status_code not in (200, 302) or "שגויים" in r.text:
        raise SystemExit(f"login failed for {email}")


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000"
    with httpx.Client(base_url=base, follow_redirects=True, timeout=120) as client:
        print("health:", client.get("/health").json())

        login(client, "cand@fit.local")
        jobs = client.get("/jobs/", params={"q": "Flask"}).text
        match = re.search(r'Python Backend</td>.*?href="/jobs/([0-9a-f-]{36})"', jobs, re.S)
        if not match:
            raise SystemExit("Python Backend not found in candidate search")
        job_id = match.group(1)
        cv = Path("samples/cv_python.txt")
        r = client.post(f"/applications/apply/{job_id}", files={"cv": (cv.name, cv.read_bytes(), "text/plain")})
        app_match = re.search(r"/applications/([0-9a-f-]{36})", str(r.url))
        if not app_match:
            already = "כבר הגשת" in r.text
            print("apply:", "already applied" if already else f"unexpected page {r.url}")
            mine = client.get("/applications/mine").text
            app_match = re.search(r"/applications/([0-9a-f-]{36})", mine)
        app_id = app_match.group(1)
        candidate_view = client.get(f"/applications/{app_id}").text
        print("application:", app_id)
        print("candidate sees report:", "ציון כולל" in candidate_view)

        login(client, "hr@fit.local")
        page = client.get(f"/applications/{app_id}").text
        status = re.search(r'class="badge[^"]*">([^<]+)<', page)
        print("hr sees status:", status.group(1) if status else "?")
        print("hr sees report:", "ציון כולל" in page)
        dashboard = client.get("/dashboard/").text
        print("dashboard lists Python Backend:", "Python Backend" in dashboard)
    return 0


if __name__ == "__main__":
    sys.exit(main())
