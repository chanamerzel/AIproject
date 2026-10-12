# 05 — מפרט סוכן הערכת מועמד

## תשתית

- **LangChain Deep Agents** — `deepagents.create_deep_agent(model, tools, system_prompt)` ב-`agent/deep_agent.py`.
- מודל: Gemini (`LLM_PROVIDER=gemini`, `GEMINI_API_KEY`) או Ollama ב-Docker (`LLM_PROVIDER=ollama`, פרופיל `ollama` ב-compose).
- הכלים `extract_resume_profile` ו-`evaluate_requirement_coverage` נקראים **רק** דרך MCP stdio (`python -m mcp_studio`).
- חיפוש רשת: שרת **Tavily MCP** (`tavily-mcp`), לא REST ישיר. שם הכלי מזוהה דינמית (`tavily_search` / `tavily-search`).
- RAG: Chroma עם all-MiniLM-L6-v2. קורות חיים נשמרים כמסמך מלא (לדירוג) וכקטעים (לציטוטים).

## למה process נפרד

המפרט דורש process עצמאי. הערכה כוללת רשת, RAG ו-LLM ולוקחת שניות עד דקות. בתוך POST של הדפדפן המשתמש ייתקע והפרדת CQRS תישבר. ב-Docker הסוכן הוא שירות `worker` נפרד מ-`web`.

## תהליך

`python -m agent.worker` רץ בלולאה (`WORKER_POLL_SECONDS`, ברירת מחדל 20) וקורא ישירות מטבלאות הקריאה.

1. בדיקה מקדימה: אם אין מודל LLM מוגדר — שגיאה בלוג, אף מועמדות לא נוגעת. אין ציון בלי סוכן.
2. לכל מועמדות `Submitted`: `ApplicationScreeningStarted`.
3. הטמעת ה-CV ב-Chroma (idempotent — מבטיח RAG גם אם ההטמעה בזמן ההגשה נכשלה).
4. הסוכן מתכנן ומפעיל: `extract_resume_profile` → `evaluate_requirement_coverage` → `rag_cv_against_job` → `tavily_web_search` (לפחות פעם אחת).
5. הסוכן מחזיר JSON. המערכת מצליבה אותו מול פלט הכלים (`_finalize`):
   - ציוני הרכיבים נלקחים מהכלים, לא ממה שהמודל טען.
   - כלי חובה שהסוכן דילג עליו מופעל ונרשם ב-`tools_skipped_by_agent`.
   - כישלון Tavily נרשם בפערים, והמשקל מחולק מחדש בין הרכיבים הקיימים.
6. `ApplicationScreeningCompleted` עם הדוח המלא.
7. כישלון: `ApplicationScreeningFailed`. אחרי 3 כישלונות הסטטוס `ScreeningFailed` ו-HR רואה את השגיאה.

## פורמט הדוח

```json
{
  "overall_score": 0,
  "skill_coverage": 0,
  "semantic_fit": 0,
  "web_score": 0,
  "recommendation": "advance|hold|reject",
  "agent_recommendation": "advance|hold|reject",
  "summary": "",
  "strengths": [],
  "gaps": [],
  "web_evidence": [{"title": "", "url": "", "finding": ""}],
  "cv_excerpts": [],
  "tools_used": [],
  "tools_skipped_by_agent": [],
  "runtime": "deepagents:gemini"
}
```

## ציון והמלצה

`overall = 0.45*skill_coverage + 0.35*semantic_fit + 0.20*web_score`  
`advance` ≥ 70 · `hold` 45–69 · `reject` < 45

## מצב בדיקות

`FITSCREEN_AGENT_MODE=pipeline` מריץ את אותם כלים בלי LLM. מיועד לסוויטת הבדיקות בלבד. בדיקה נפרדת מריצה את לולאת `create_deep_agent` עם מודל מתוסרט ומוודאת שהכלים נקראו ושהדוח הוצלב.
