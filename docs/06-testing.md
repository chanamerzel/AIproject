# 06 — בדיקות

מסגרת: `pytest`. הרצה: `python -m pytest tests -q`.

## מקרי חובה לפי פיצ'ר

| פיצ'ר | בדיקה |
|---|---|
| F1 | הרשמה יוצרת UserRegistered; התחברות נכשלת בסיסמה שגויה; מועמד לא ניגש לדשבורד HR; דלת מגייסים מחייבת תפקיד, דלת מועמדים מתעלמת מתפקיד מזויף, וכל דלת עוצרת את הסוג השני; Google (מוחלף ב-monkeypatch) רושם `auth_provider=google`, לוקח את התפקיד מהדלת, נכנס לחשבון קיים, ודוחה אימייל לא מאומת (`tests/test_doors_google.py`) |
| F2 | HR יוצר Draft; רק HiringManager פותח וסוגר משרה; הוא רואה טיוטה ממתינה ברשימת המשרות ובלוח; HiringManager לא כותב משרה ולא מחליט (`tests/test_jobs.py`) |
| F3 | חיפוש מחזיר משרה פתוחה לפי מילת מפתח; רשימת המשרות היא כרטיסים עם דפדוף וספירת משרות פתוחות, בלי טבלה (`tests/test_jobs.py`) |
| F4 | הגשה יוצרת ApplicationSubmitted ומעלה applicant_count |
| F5 | דשבורד סופר משרות Open ונרשמים; טבלת הלוח מדפדפת והסיכום נשאר על כל המשרות (`tests/test_apply_dashboard.py`) |
| F6 | הטמעת שני CV שונים מחזירה דירוג סמנטי |
| F7 | worker על מועמדות Submitted מייצר ScreeningCompleted עם ציון |
| F8 | Reject משנה סטטוס ונרשם אירוע; ה-view לא שולח ולא רושם מייל; ה-worker שולח פעם אחת לכל החלטה ורושם `DecisionEmailSent`; כישלון רושם `DecisionEmailFailed` ונעצר אחרי 3; בלי התחברות ל-Gmail לא נשלח ולא נרשם כלום (`tests/test_decision_email.py`, Gmail מוחלף ב-monkeypatch) |
| F9 | דירוג: מוערכים לפי ציון, לא-מוערכים אחריהם לפי דמיון וקטורי; סיכום המלצות; מועמד לא ניגש לדף |
| F10 | בקשת הערכה חוזרת כותבת אירוע, מחזירה ל-Submitted, ההיסטוריה מציגה שני ציונים והפרש; מועמד לא יכול לבקש; אחרי 3 כישלונות הבקשה נותנת ניסיונות חדשים |
| F11 | מודל מתוסרט עובר orchestrator → cv-analyst → web-researcher; כל כלי חובה נקרא, ו-`delegation` מראה איזה תת-סוכן קרא לו; `auto` בוחר Gemini ואז Ollama |

## CI (GitHub Actions)

`.github/workflows/tests.yml` רץ בכל push:

- `sqlite`: כל הסוויטה.
- `sql-server`: אותה סוויטה מול SQL Server 2022, אותו מנוע כמו Somee.
- `docker`: `docker compose build`.

## בדיקה ידנית מול השירותים האמיתיים

1. `docker compose up -d --build`, ואז `docker compose exec web python seed_demo.py`.
2. `python -m scripts.smoke_flow http://127.0.0.1:5050`: הגשה, הערכת סוכן, החלטה.
3. `docker compose logs worker`: שורת `screened ... runtime=deepagents:gemini:...`.
4. `/health`: `"backend": "mssql"` (Somee).

## בדיקות ארכיטקטורה

- Command כותב ל-`events` לפני עדכון פרויקציה.
- Query לא קורא ל-`event_store.append`.
- אין מחרוזות נושא-טיסות בקוד המוצר (`app/`, `templates/`).
