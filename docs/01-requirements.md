# 01 — דרישות וסטטוס ציות

מזהים: `FR-*` פונקציונלי, `NFR-*` לא-פונקציונלי.  
סטטוס: **מולא** = הקוד קיים, יש בדיקה אוטומטית, והשירות החיצוני חובר ונבדק בהרצה אמיתית.

## פונקציונלי

| מזהה | דרישת קורס | מימוש | סטטוס |
|---|---|---|---|
| FR-1 | בחירת נושא | גיוס מועמדים | מולא |
| FR-2 | משתמשים + אותנטיקציה | שתי דלתות (מועמדים / מגייסים), סיסמה ב-hash, session, וכניסה עם Google (OpenID Connect) | מולא. Google פעיל אחרי הגדרת OAuth client ב-`.env` |
| FR-3 | שני סוגי משתמשים לפחות | שלושה: מועמד, מגייסת, מנהל גיוס, כל אחד עם סמכות נפרדת (F1) | מולא |
| FR-4.1 | חיפוש | חיפוש משרות + חיפוש סמנטי של מועמדים | מולא |
| FR-4.2 | פרטי תוצאה | דף משרה + דף מועמדות עם דוח סוכן והיסטוריית הערכות | מולא |
| FR-4.3 | טבלה | כרטיסי משרות עם דפדוף, טבלת מועמדים, טבלת דירוג (F9) | מולא |
| FR-4.4 | דשבורד משרות פתוחות + נרשמים | כרטיסים, טבלה, Chart.js | מולא |
| FR-4.5 | הזנת נתונים | משרה, CV, החלטת HR, בקשת הערכה חוזרת | מולא |
| FR-5 | סוכן ב-process נפרד: קריאה מ-DB, אינטרנט, RAG, הערכת סטטוס | קונטיינר `worker` נפרד, Deep Agent עם תתי-סוכנים, Chroma, Tavily MCP | מולא (הרצה אמיתית עם Gemini: ציון 83, 157 שניות) |

## לא-פונקציונלי

| מזהה | דרישת קורס | מימוש | סטטוס |
|---|---|---|---|
| NFR-1 | סדרת MD | `docs/00`–`08` | מולא |
| NFR-2 | Skill מ-skills.sh | `flask-python` הותקן ב-`npx skills add mindrally/skills` (`skills-lock.json`) | מולא |
| NFR-3 | Skill + Rule מקומיים | `.cursor/skills/` (2) + `.cursor/rules/sdad.mdc` | מולא |
| NFR-4 | Flask | `app/`, gunicorn ב-Docker | מולא |
| NFR-5 | DB בענן (Somee) | `mssql+pymssql` מול `fitscreen.mssql.somee.com`, יצירת סכמה אוטומטית, `/health`; הסוויטה רצה מול SQL Server ב-CI | מולא (התחברות ל-Somee נבדקה) |
| NFR-6 | הטמעת CV + חיפוש סמנטי | Chroma + all-MiniLM-L6-v2, פיצול לקטעים, דירוג מועמדים (F9); hash רק בבדיקות | מולא |
| NFR-7 | CQRS/MVC | `views` / `commands` / `queries` | מולא |
| NFR-8 | ענן + Event Sourcing | `events` append-only ב-Somee + פרויקציות + `app.replay` + היסטוריית הערכות מהאירועים (F10) | מולא |
| NFR-9 | שירותים חיצוניים ב-MCP | Tavily דרך `tavily-mcp` (stdio) בסוכן. Gmail דרך `gmail-mcp` (`@gongrzhe/server-gmail-autoauth-mcp`, stdio): ה-worker שולח מייל החלטה למועמד ורושם `DecisionEmailSent` / `DecisionEmailFailed` | מולא (Tavily). Gmail: הקוד והבדיקות קיימים, ההתחברות ל-Google בקונטיינר נבדקה עד ה-callback; שליחה אמיתית ממתינה ל-OAuth client של המשתמשת |
| NFR-10 | שני Tools מ-MCP Studio | שרת `python -m mcp_studio`, נקרא בפרוטוקול MCP | מולא |
| NFR-11 | Deep Agent + RAG + Tavily | `create_deep_agent` עם מתזמר ותתי-סוכנים `cv-analyst` ו-`web-researcher` (F11); Gemini, Ollama כגיבוי | מולא |
| NFR-12 | GitHub | [smerzel/AIproject](https://github.com/smerzel/AIproject), CI ב-`.github/workflows/tests.yml` (sqlite, sql-server, docker) | מולא |

## כללי מוצר

- כתיבה עסקית רק דרך Command → Event → Projection.
- Query לא כותב לטבלאות קריאה.
- בלי מודל LLM ה-worker לא מעריך מועמדויות; אין ציון בלי סוכן.
