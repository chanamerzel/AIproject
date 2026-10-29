# FitScreen

מערכת גיוס: HR פותח משרה, מועמד מגיש קורות חיים, וסוכן בתהליך נפרד נותן ציון. הכתיבה נשמרת כאירועים. הקריאה היא ממסכים.

שני תהליכים, לא אחד:

- `web` מציג את האתר. הוא לא מריץ את מודל השפה.
- `worker` קורא מועמדויות שהוגשו, מפעיל Deep Agent (שני תתי-סוכנים), וכותב את הציון בחזרה.

הציון: 45% כיסוי כישורי חובה, 35% דמיון סמנטי מ-Chroma, 20% ראיות מהרשת. Tavily מחפש את השם המלא; GitHub נבדק כתיק ציבורי מול המשרה. המספרים נלקחים מפלט הכלים.

## מה עדיין לא גמור

- Gmail שולח מייל רק אחרי חיבור OAuth. עד אז ההחלטה נשמרת והמייל נשאר "ממתין לשליחה". ההקמה בסעיף Gmail למטה.
- חיפוש סמנטי עם `all-MiniLM-L6-v2`, מודל שעובד טוב על אנגלית. קורות החיים בדמו באנגלית.
- PDF שהוא סריקה (תמונה) לא נקרא.

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
  W --> GM[Gmail MCP - מייל החלטה]
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

### Gmail (מייל החלטה)

פעם אחת. קבצי ההתחברות נשמרים ב-`secrets/gmail/`, שלא נכנס ל-git ולא לתמונת ה-Docker.

1. [Google Cloud Console](https://console.cloud.google.com/): פרויקט חדש → APIs & Services → Library → **Gmail API** → Enable.
2. OAuth consent screen: סוג External, שם אפליקציה ומייל, וב-Test users להוסיף את חשבון ה-Gmail שישלח את המיילים.
3. Credentials → Create credentials → OAuth client ID → סוג **Desktop app** → Download JSON. לשמור בשם `secrets/gmail/gcp-oauth.keys.json`.
4. `docker compose up --build -d` (התמונה צריכה את `gmail-mcp` וה-worker צריך את התיקייה).
5. `powershell -ExecutionPolicy Bypass -File scripts\gmail_auth.ps1` → הדפדפן נפתח → כניסה לחשבון → אישור. בסוף נוצר `secrets/gmail/credentials.json`.

ה-worker קולט את ההתחברות בסבב הבא, בלי הפעלה מחדש. אפליקציה במצב Testing מקבלת token ל-7 ימים; אחרי זה מריצים שוב את שלב 5. חשבונות `seed_demo.py` הם `@fit.local`, ולכן לדמו של מייל צריך מועמד שנרשם עם כתובת אמיתית.

### כניסה עם Google

נפרד מ-Gmail. אפשר באותו פרויקט ב-Google Cloud.

1. OAuth consent screen: אם הוא במצב Testing, להוסיף ב-Test users כל חשבון שינסה להיכנס.
2. Credentials → Create credentials → OAuth client ID → סוג **Web application**.
3. Authorized redirect URIs: `http://localhost:5050/auth/google/callback` (הפורט לפי `WEB_PORT`). נכנסים לאתר דרך `localhost`, באותה כתובת.
4. ב-`.env`: `GOOGLE_CLIENT_ID=...` ו-`GOOGLE_CLIENT_SECRET=...`, ואז `docker compose up -d --build`.

בלי המפתחות הכפתור לא מוצג, והכניסה בסיסמה עובדת כרגיל.

## הרצה מקומית (פיתוח)

```powershell
pip install -r requirements.txt
copy .env.example .env
python seed_demo.py
python wsgi.py            # מסוף 1
python -m agent.worker    # מסוף 2
```

חשבונות אחרי `seed_demo.py` (סיסמה `secret1`): `hr@fit.local` (מגייסת), `hm@fit.local` (מנהל גיוס), `cand@fit.local`, `cand2@fit.local` (מועמדים). מגייסים נכנסים ב-`/auth/recruit/login`, מועמדים ב-`/auth/login`. הרשמת מועמד יוצרת מועמד בלבד; הרשמת מגייס (`/auth/recruit/register`) מבקשת לבחור מגייסת או מנהל גיוס. אם פורט 5000 תפוס, משנים `WEB_PORT` ב-`.env`.  
קורות חיים לדוגמה: `samples/cv_python.txt`, `samples/cv_unrelated.txt`.

## דמו למרצה (5 דקות)

1. `/health` — מראה שהמסד הוא SQL Server ב-Somee.
2. כניסה כ-HR → משרה חדשה (נשמרת כטיוטה).
3. כניסה כמנהל גיוס → אישור פתיחת המשרה לקבלת מועמדויות.
4. כניסה כמועמד → חיפוש "Flask" → פרטי משרה → העלאת CV.
5. ב-`docker compose logs worker` מופיעה שורת `screened ... runtime=deepagents:gemini:...`.
6. כניסה כ-HR → דשבורד (משרות פתוחות + מספר נרשמים) → משרה → **דירוג מועמדים** → דוח: ציון מפורק, קטעי CV מ-RAG, ראיות Tavily עם קישורים, וטבלה שמראה איזה תת-סוכן הפעיל איזה כלי.
7. **הערכה חוזרת** עם נימוק → אחרי סבב של ה-worker, "היסטוריית הערכות" מציגה את שני הציונים והשינוי.
8. החלטה → ציר זמן אירועים מתעדכן, ואחרי סבב של ה-worker הכרטיס "מייל למועמד" מראה "מייל נשלח ל-..." (Gmail MCP). `python -m app.replay` בונה את טבלאות הקריאה מחדש מהאירועים בלבד.

## Somee (NFR-5, NFR-8)

Somee מארח **SQL Server בלבד**; Flask וה-worker רצים ב-Docker ומתחברים מרחוק.

1. [somee.com](https://somee.com) → הרשמה → User Panel → Databases → Create MS SQL (2019/2022).
2. ב-`.env`: `DATABASE_URL=mssql+pymssql://LOGIN:PASSWORD@YOURDB.mssql.somee.com:1433/YOURDB`
3. בדיקה: `python -m scripts.check_db` — יוצר סכמה ומדפיס ספירות.

תקלות נפוצות: סיסמה עם `@`/`#` חייבת URL-encoding (`%40`, `%23`); פורט 1433 חסום ברשת; גישה מרחוק לא מאופשרת ב-panel. בלי `DATABASE_URL` המערכת נופלת ל-SQLite מקומי — זה מצב פיתוח, לא מצב הגשה.

## Deep Agent, RAG ו-MCP (NFR-6, 9, 10, 11)

- **Deep Agent:** `deepagents.create_deep_agent` ב-[agent/deep_agent.py](agent/deep_agent.py). מתזמר מתכנן ומאציל לשני תתי-סוכנים: `cv-analyst` (MCP Studio + RAG) ו-`web-researcher` (Tavily, כולל קישור GitHub מהקורות חיים). הדוח מוצלב מול פלט הכלים, וכלי שדילגו עליו מופעל ומסומן. `web_score` מחושב מהקישורים שחזרו.
- **בלי מודל LLM ה-worker לא מעריך** — הוא כותב שגיאה בלוג ומשאיר את המועמדות בתור. אין ציון "שקט" בלי סוכן.
- **RAG:** Chroma עם all-MiniLM-L6-v2 (ONNX). קורות חיים מפוצלים לקטעים; חיפוש סמנטי במסך HR ובסוכן.
- **MCP Studio:** `extract_resume_profile` (כישורים, מעסיק, קישור GitHub) ו-`evaluate_requirement_coverage` (כיסוי דרישות לפי מילה שלמה) — שרת stdio `python -m mcp_studio`, נקרא בפרוטוקול MCP.
- **Tavily:** שרת `tavily-mcp` דרך MCP.
- **Gmail:** שרת `gmail-mcp` דרך MCP. אחרי החלטת HR ה-worker שולח למועמד מייל בעברית ורושם `DecisionEmailSent` או `DecisionEmailFailed`. ה-view לא שולח בעצמו. בלי התחברות ל-Gmail המייל נשאר "ממתין לשליחה". הקמה בסעיף [Gmail](#gmail-מייל-החלטה).

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
| [docs/09-demo.md](docs/09-demo.md) | תסריט הדגמה |
| [docs/10-oral.md](docs/10-oral.md) | מיפוי מושגי המצגות לקבצים |

Skill מ-skills.sh: `.agents/skills/flask-python`. Skills מקומיים: `.cursor/skills/`. Rule: `.cursor/rules/sdad.mdc`.

## בדיקות

```powershell
python -m pytest tests -q
```

הבדיקות רצות אופליין (embedding hash, צינור כלים בלי LLM). `TEST_DATABASE_URL=mssql+pymssql://...` מריץ את כל הסוויטה מול SQL Server. ב-GitHub Actions רצות שלוש משימות: SQLite, SQL Server, ובניית Docker.
