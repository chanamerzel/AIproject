# 07 — עקיבות דרישה → פיצ'ר → קוד

| דרישה | פיצ'ר | קוד עיקרי |
|---|---|---|
| FR-1 נושא משרות | כולו | `docs/00-vision.md` |
| FR-2 Auth | F1 | `app/views/auth.py`, `app/commands/identity.py` |
| FR-3 תפקידים | F1 | `app/security.py` |
| FR-4.1 חיפוש | F3, F6 | `app/queries/jobs.py`, `app/queries/semantic.py` |
| FR-4.2 פרטים | F3, F8 | `app/views/jobs.py`, `app/views/applications.py` |
| FR-4.3 טבלה | F3, F5 | templates `jobs/table.html`, `applications/table.html` |
| FR-4.4 דשבורד | F5 | `app/views/dashboard.py` |
| FR-4.5 הזנה | F2, F4, F8 | commands `jobs`, `applications`, `decisions` |
| FR-5 סוכן | F7 | `agent/worker.py` (קריאה מ-DB), `agent/deep_agent.py`, `agent/mcp_client.py` |
| NFR-1 MD | — | `docs/` |
| NFR-2 skills.sh | — | `.agents/skills/` |
| NFR-3 Skill+Rule | — | `.cursor/skills/`, `.cursor/rules/sdad.mdc` |
| NFR-4 Flask | — | `wsgi.py`, `app/` |
| NFR-5 Somee | — | `app/db.py` |
| NFR-6 Vector | F4, F6, F7 | `agent/rag.py`, `app/queries/semantic.py` |
| NFR-7 CQRS/MVC | — | `commands/`, `queries/`, `views/` |
| NFR-8 Event Sourcing | — | `app/event_store.py`, `app/projections.py` |
| NFR-9 MCP חיצוני | F7 | `agent/mcp_client.py` → Tavily MCP; Gmail MCP עדיין לא מחובר |
| NFR-10 MCP Studio | F7 | `mcp_studio/extract_resume_profile.py`, `mcp_studio/evaluate_requirement_coverage.py`, `mcp_studio/tools.json` |
| NFR-11 Deep Agent | F7 | `agent/deep_agent.py`, `agent/worker.py` |
| NFR-12 Git | — | `.gitignore`, `README.md` |
