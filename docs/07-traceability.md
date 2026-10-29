# 07 — עקיבות דרישה → פיצ'ר → קוד → בדיקה

| דרישה | פיצ'ר | קוד עיקרי | בדיקה |
|---|---|---|---|
| FR-1 נושא משרות | כולו | `docs/00-vision.md` | `tests/test_architecture.py` (אין שפת טיסות) |
| FR-2 Auth | F1 | `app/views/auth.py`, `app/commands/identity.py`, `app/google_auth.py` | `tests/test_identity.py`, `tests/test_doors_google.py` |
| FR-3 תפקידים | F1 | `app/security.py`, `app/views/auth.py`, `app/views/jobs.py`, `app/views/applications.py` | `tests/test_identity.py`, `tests/test_jobs.py`, `tests/test_doors_google.py`, `tests/test_access_and_tools.py` |
| FR-4.1 חיפוש | F3, F6 | `app/queries/jobs.py`, `app/queries/semantic.py` | `tests/test_jobs.py`, `tests/test_semantic_agent.py` |
| FR-4.2 פרטים | F3, F8, F10 | `app/views/jobs.py`, `app/views/applications.py` | `tests/test_ranking_rescreen.py` |
| FR-4.3 טבלה | F3, F5, F9 | `jobs/table.html`, `jobs/ranking.html`, `app/queries/jobs.py`, `app/queries/ranking.py` | `tests/test_jobs.py`, `tests/test_ranking_rescreen.py` |
| FR-4.4 דשבורד | F5 | `app/views/dashboard.py` | `tests/test_apply_dashboard.py` |
| FR-4.5 הזנה | F2, F4, F8, F10 | `app/commands/jobs.py`, `app/commands/applications.py` | `tests/test_jobs.py`, `tests/test_apply_dashboard.py`, `tests/test_ranking_rescreen.py`, `tests/test_decision_email.py` |
| FR-5 סוכן | F7, F11 | `agent/worker.py` (קריאה מ-DB), `agent/deep_agent.py`, `agent/mcp_client.py` | `tests/test_deep_agent.py` |
| NFR-1 MD | — | `docs/` | — |
| NFR-2 skills.sh | — | `.agents/skills/flask-python`, `skills-lock.json` | — |
| NFR-3 Skill+Rule | — | `.cursor/skills/`, `.cursor/rules/sdad.mdc` | — |
| NFR-4 Flask | — | `wsgi.py`, `app/` | כל הסוויטה |
| NFR-5 Somee | — | `app/db.py`, `scripts/check_db.py` | CI `sql-server` |
| NFR-6 Vector | F4, F6, F7, F9 | `agent/rag.py`, `app/queries/semantic.py`, `app/queries/ranking.py` | `tests/test_semantic_agent.py`, `tests/test_ranking_rescreen.py` |
| NFR-7 CQRS/MVC | — | `commands/`, `queries/`, `views/` | `tests/test_architecture.py` |
| NFR-8 Event Sourcing | F10 | `app/event_store.py`, `app/projections.py`, `app/replay.py` | `tests/test_mcp_and_replay.py`, `tests/test_ranking_rescreen.py` |
| NFR-9 MCP חיצוני | F7, F8 | `agent/mcp_client.py` → Tavily MCP (`call_tavily_search`) ו-Gmail MCP (`call_gmail_send`); `agent/notifier.py`, `app/queries/notifications.py`, `scripts/gmail_auth.ps1` | `tests/test_decision_email.py` (Gmail מוחלף ב-monkeypatch) |
| NFR-10 MCP Studio | F7 | `mcp_studio/extract_resume_profile.py`, `mcp_studio/evaluate_requirement_coverage.py`, `mcp_studio/tools.json` | `tests/test_mcp_and_replay.py`, `tests/test_access_and_tools.py` |
| NFR-11 Deep Agent | F7, F11 | `agent/deep_agent.py` (מתזמר + `cv-analyst` + `web-researcher`), `agent/worker.py` | `tests/test_deep_agent.py` |
| NFR-12 Git | — | [smerzel/AIproject](https://github.com/smerzel/AIproject), `.github/workflows/tests.yml` | CI |
