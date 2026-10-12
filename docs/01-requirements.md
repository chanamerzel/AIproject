# 01 — דרישות וסטטוס ציות

מזהים: `FR-*` פונקציונלי, `NFR-*` לא-פונקציונלי.  
סטטוס: **מולא** / **ממתין לחשבון** (הקוד מוכן ונבדק; חסר חשבון/מפתח חיצוני שרק בעלת הפרויקט יכולה לפתוח).

## פונקציונלי

| מזהה | דרישת קורס | מימוש | סטטוס |
|---|---|---|---|
| FR-1 | בחירת נושא | גיוס מועמדים | מולא |
| FR-2 | משתמשים + אותנטיקציה | הרשמה, כניסה, session, hash | מולא |
| FR-3 | שני סוגי משתמשים לפחות | Candidate, HR, HiringManager | מולא |
| FR-4.1 | חיפוש | חיפוש משרות + חיפוש סמנטי של מועמדים | מולא |
| FR-4.2 | פרטי תוצאה | דף משרה + דף מועמדות עם דוח סוכן | מולא |
| FR-4.3 | טבלה | טבלת משרות ומועמדים | מולא |
| FR-4.4 | דשבורד משרות פתוחות + נרשמים | כרטיסים, טבלה, Chart.js | מולא |
| FR-4.5 | הזנת נתונים | משרה, CV, החלטת HR | מולא |
| FR-5 | סוכן ב-process נפרד: קריאה מ-DB, אינטרנט, RAG, הערכת סטטוס | קונטיינר `worker` נפרד, Deep Agent, Chroma, Tavily MCP | ממתין למפתחות Tavily + Gemini |

## לא-פונקציונלי

| מזהה | דרישת קורס | מימוש | סטטוס |
|---|---|---|---|
| NFR-1 | סדרת MD | `docs/00`–`07` | מולא |
| NFR-2 | Skill מ-skills.sh | `flask-python` הותקן ב-`npx skills add mindrally/skills` (`skills-lock.json`) | מולא |
| NFR-3 | Skill + Rule מקומיים | `.cursor/skills/` (2) + `.cursor/rules/sdad.mdc` | מולא |
| NFR-4 | Flask | `app/`, gunicorn ב-Docker | מולא |
| NFR-5 | DB בענן (Somee) | `mssql+pymssql`, יצירת סכמה אוטומטית, `/health`, `scripts/check_db.py`; הסוויטה רצה מול SQL Server ב-CI | ממתין לחשבון Somee |
| NFR-6 | הטמעת CV + חיפוש סמנטי | Chroma + all-MiniLM-L6-v2, פיצול לקטעים; hash רק בבדיקות | מולא |
| NFR-7 | CQRS/MVC | `views` / `commands` / `queries` | מולא |
| NFR-8 | ענן + Event Sourcing | `events` append-only + פרויקציות + `app.replay`, על אותו Somee | ממתין לחשבון Somee |
| NFR-9 | שירותים חיצוניים ב-MCP | Tavily דרך `tavily-mcp` (stdio). Gmail לא מחובר | ממתין למפתח Tavily |
| NFR-10 | שני Tools מ-MCP Studio | שרת `python -m mcp_studio`, נקרא בפרוטוקול MCP | מולא |
| NFR-11 | Deep Agent + RAG + Tavily | `deepagents.create_deep_agent` עם 4 כלים; Gemini או Ollama | ממתין למפתח Gemini (או Ollama) |
| NFR-12 | GitHub | workflow ב-`.github/workflows/tests.yml`; ריפו מרוחק אחרי `gh auth login` | ממתין לחשבון GitHub |

## כללי מוצר

- כתיבה עסקית רק דרך Command → Event → Projection.
- Query לא כותב לטבלאות קריאה.
- בלי מודל LLM ה-worker לא מעריך מועמדויות; אין ציון בלי סוכן.
