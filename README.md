# FitScreen

מערכת מידע לגיוס מועמדים לפי **SDAD**: קודם מסמכי `docs/`, אחר כך פיצ'ר שלם (מסך + Command/Query + אירוע + בדיקה).

התחום נעול: **משרות ומועמדים בלבד** (סעיפי הקורס 4.4, NFR-6, NFR-11).

## תרשים מערכת

```mermaid
flowchart LR
  UI[Flask Jinja] --> CMD[Commands]
  CMD --> ES[(events - Somee MS SQL)]
  ES --> PR[Projections]
  PR --> Q[(users / jobs / applications)]
  UI --> Q
  W[Deep Agent worker - container] --> Q
  W --> CMD
  W --> CH[(Chroma - MiniLM embeddings)]
  W --> MCP[MCP Studio server]
  W --> TV[Tavily MCP]
  W --> LLM[Gemini, Ollama כגיבוי]
```

## הרצה ב-Docker (מסלול ההגשה)

1. Docker Desktop פועל (`docker info` מחזיר גרסת Server).
2. `copy .env.example .env` ומילוי `DATABASE_URL` (Somee), `TAVILY_API_KEY`, `GEMINI_API_KEY`.
3. ברשת שמסננת HTTPS (Symen / NetFree): `powershell -ExecutionPolicy Bypass -File scripts\export_proxy_cert.ps1`. בלי זה הקונטיינר נכשל באימות SSL מול Tavily, Gemini והורדת המודל.
4. הרצה:

```powershell
docker compose up --build -d
docker compose exec web python seed_demo.py
docker compose logs -f worker
```

- אפליקציה: http://127.0.0.1:5000 (או `WEB_PORT` מ-`.env`) · בריאות: `/health` (מציג `mssql` מול `sqlite`, ספירות טבלאות, ומודל ה-embedding)
- `web` ו-`worker` הם שני תהליכים נפרדים מאותו אימג'. הסוכן לא רץ בתוך בקשת HTTP.

### מודל השפה של הסוכן

`LLM_PROVIDER=auto` (ברירת מחדל): Gemini, ואם אין מפתח או שההרצה נכשלה, Ollama שמותקן על Windows.

- Ollama: התקנה מ-[ollama.com/download/windows](https://ollama.com/download/windows), ואז `ollama pull qwen2.5:3b`. ה-worker מגיע אליו דרך `OLLAMA_BASE_URL=http://host.docker.internal:11434`.
- `LLM_PROVIDER=gemini` או `LLM_PROVIDER=ollama` מכריחים מודל אחד.
- על מחשב בלי כרטיס מסך Ollama איטי מאוד (יותר מ-10 דקות להערכה), ולכן הוא גיבוי ולא ראשי. פירוט ב-[docs/08-decisions.md](docs/08-decisions.md).

## הרצה מקומית (פיתוח)

```powershell
pip install -r requirements.txt
copy .env.example .env
python seed_demo.py
python wsgi.py            # מסוף 1
python -m agent.worker    # מסוף 2
```

חשבונות אחרי `seed_demo.py` (סיסמה `secret1`): `hr@fit.local` (גיוס), `hm@fit.local` (מנהל גיוס), `cand@fit.local`, `cand2@fit.local` (מועמדים).  
קורות חיים לדוגמה: `samples/cv_python.txt`, `samples/cv_unrelated.txt`.

## דמו למרצה (5 דקות)

1. `/health` — מראה שהמסד הוא SQL Server ב-Somee.
2. כניסה כ-HR → משרה חדשה (נשמרת כטיוטה).
3. כניסה כמנהל גיוס → אישור פתיחה.
4. כניסה כמועמד → חיפוש "Flask" → פרטי משרה → העלאת CV.
5. ב-`docker compose logs worker` מופיעה שורת `screened ... runtime=deepagents:gemini:...`.
6. כניסה כ-HR → דשבורד (משרות פתוחות + מספר נרשמים) → משרה → **דירוג מועמדים** → דוח: ציון מפורק, קטעי CV מ-RAG, ראיות Tavily עם קישורים, וטבלה שמראה איזה תת-סוכן הפעיל איזה כלי.
7. **הערכה חוזרת** עם נימוק → אחרי סבב של ה-worker, "היסטוריית הערכות" מציגה את שני הציונים והשינוי.
8. החלטה → ציר זמן אירועים מתעדכן. `python -m app.replay` בונה את טבלאות הקריאה מחדש מהאירועים בלבד.

## Somee (NFR-5, NFR-8)

Somee מארח **SQL Server בלבד**; Flask וה-worker רצים ב-Docker ומתחברים מרחוק.

1. [somee.com](https://somee.com) → הרשמה → User Panel → Databases → Create MS SQL (2019/2022).
2. ב-`.env`: `DATABASE_URL=mssql+pymssql://LOGIN:PASSWORD@YOURDB.mssql.somee.com:1433/YOURDB`
3. בדיקה: `python -m scripts.check_db` — יוצר סכמה ומדפיס ספירות.

תקלות נפוצות: סיסמה עם `@`/`#` חייבת URL-encoding (`%40`, `%23`); פורט 1433 חסום ברשת; גישה מרחוק לא מאופשרת ב-panel. בלי `DATABASE_URL` המערכת נופלת ל-SQLite מקומי — זה מצב פיתוח, לא מצב הגשה.

## Deep Agent, RAG ו-MCP (NFR-6, 9, 10, 11)

- **Deep Agent:** `deepagents.create_deep_agent` ב-[agent/deep_agent.py](agent/deep_agent.py). מתזמר מתכנן ומאציל לשני תתי-סוכנים: `cv-analyst` (MCP Studio + RAG) ו-`web-researcher` (Tavily). הדוח מוצלב מול פלט הכלים, וכלי שדילגו עליו מופעל ומסומן.
- **בלי מודל LLM ה-worker לא מעריך** — הוא כותב שגיאה בלוג ומשאיר את המועמדות בתור. אין ציון "שקט" בלי סוכן.
- **RAG:** Chroma עם all-MiniLM-L6-v2 (ONNX). קורות חיים מפוצלים לקטעים; חיפוש סמנטי במסך HR ובסוכן.
- **MCP Studio:** `extract_resume_profile`, `evaluate_requirement_coverage` — שרת stdio `python -m mcp_studio`, נקרא בפרוטוקול MCP.
- **Tavily:** שרת `tavily-mcp` דרך MCP.
- **Gmail:** לא מחובר. ההחלטה נשמרת כאירוע; המייל לא נשלח. הדרישה החיצונית (NFR-9) מתמלאת ב-Tavily.

## מסמכי SDAD

| קובץ | תוכן |
|---|---|
| [docs/00-vision.md](docs/00-vision.md) | חזון |
| [docs/01-requirements.md](docs/01-requirements.md) | FR/NFR וסטטוס |
| [docs/02-architecture.md](docs/02-architecture.md) | MVC + CQRS + תהליכים |
| [docs/03-data-and-events.md](docs/03-data-and-events.md) | Event Store ופרויקציות |
| [docs/04-features.md](docs/04-features.md) | F1–F11 |
| [docs/05-agent-spec.md](docs/05-agent-spec.md) | Deep Agent |
| [docs/06-testing.md](docs/06-testing.md) | בדיקות |
| [docs/07-traceability.md](docs/07-traceability.md) | דרישה → קוד → בדיקה |
| [docs/08-decisions.md](docs/08-decisions.md) | החלטות טכניות: אפשרויות, בחירה, נימוק |

Skill מ-skills.sh: `.agents/skills/flask-python`. Skills מקומיים: `.cursor/skills/`. Rule: `.cursor/rules/sdad.mdc`.

## בדיקות

```powershell
python -m pytest tests -q
```

הבדיקות רצות אופליין (embedding hash, צינור כלים בלי LLM). `TEST_DATABASE_URL=mssql+pymssql://...` מריץ את כל הסוויטה מול SQL Server. ב-GitHub Actions רצות שלוש משימות: SQLite, SQL Server, ובניית Docker.
