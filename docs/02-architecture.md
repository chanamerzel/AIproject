# 02 — ארכיטקטורה

## תרשים רכיבים

```mermaid
flowchart TB
  subgraph MVC["שכבת MVC — app/views"]
    VAuth[auth]
    VJobs[jobs]
    VApps[applications]
    VDash[dashboard]
    VInt[internal API]
  end
  subgraph CQRS["שכבת CQRS"]
    CMD[commands]
    QRY[queries]
  end
  subgraph Write["כתיבה"]
    ES[EventStore.append]
    PR[projections.apply]
  end
  subgraph Read["קריאה"]
    TUsers[users]
    TJobs[jobs]
    TApps[applications]
  end
  VAuth --> CMD
  VJobs --> CMD
  VJobs --> QRY
  VApps --> CMD
  VApps --> QRY
  VDash --> QRY
  VInt --> CMD
  CMD --> ES
  ES --> PR
  PR --> TUsers
  PR --> TJobs
  PR --> TApps
  QRY --> TUsers
  QRY --> TJobs
  QRY --> TApps
```

## סגנון

שרת Flask במבנה **MVC** לשכבת ה-HTTP, ושירותים פנימיים ב-**CQRS**:

- **Command model:** ולידציה, לוגיקה, append ל-Event Store, הפעלת פרויקציה.
- **Query model:** קריאה בלבד מטבלאות פרויקציה (משרות, מועמדויות, דשבורד).

זה תואם לתרשים 1 של הקורס: שינוי מה-UI הולך ל-Command; תצוגות מתעדכנות מ-Query.

## תהליכים

1. **Web (Flask, gunicorn)**: ממשק משתמש. יש גם API פנימי מוגן במפתח (`/internal/...`, כותרת `X-Agent-Key`) למקרה שסוכן ירוץ על מכונה בלי גישה ישירה למסד.
2. **Worker (Deep Agent)**: process נפרד, קונטיינר `worker`. **קורא רשומות ממסד הנתונים** (`pending_screening`), מריץ `deepagents` עם מתזמר ושני תתי-סוכנים, כלי MCP Studio, Tavily MCP ו-RAG, וכותב אירועים דרך ה-Commands.
3. **Somee SQL Server**: Event Store ופרויקציות בענן.
4. **Chroma**: וקטורי CV על volume משותף ל-web ול-worker (`/app/chroma_data`).
5. **LLM**: Gemini (ענן), ו-Ollama על Windows כגיבוי (`host.docker.internal:11434`).

## זרימת כתיבה

```
UI POST → View → Command handler → EventStore.append
  → Projection.apply → Query tables
```

## זרימת קריאה

```
UI GET → View → Query handler → SELECT מטבלאות פרויקציה
```

## זרימת סוכן (תרשים 2)

```mermaid
sequenceDiagram
  participant W as agent.worker
  participant DB as Somee
  participant O as Orchestrator
  participant CA as cv-analyst
  participant WR as web-researcher
  participant MS as MCP Studio
  participant CH as Chroma
  participant TV as Tavily MCP
  W->>DB: SELECT applications WHERE status=Submitted
  W->>DB: ApplicationScreeningStarted
  W->>O: application brief
  O->>CA: task
  CA->>MS: extract_resume_profile, evaluate_requirement_coverage
  CA->>CH: rag_cv_against_job
  CA-->>O: findings
  O->>WR: task: last company + core skill
  WR->>TV: tavily_search
  WR-->>O: findings with URLs
  O-->>W: JSON report
  W->>W: _finalize: cross-check with tool trace
  W->>DB: ApplicationScreeningCompleted
```

תהליך נפרד חובה: `python -m agent.worker`. Flask לבדו לא מעריך מועמדים.

## אבטחה

- Cookie session.
- `@login_required` + `@role_required`.
- מפתח פנימי `AGENT_API_KEY` לקריאות ה-worker.

## תלות חיצונית

| שירות | פרוטוקול | תפקיד |
|---|---|---|
| Somee | TDS/SQL | Event Store + read models |
| Tavily | MCP (stdio, `tavily-mcp`) | חיפוש אינטרנט |
| Gmail | MCP | מייל החלטה (לא מחובר; ההחלטה נשמרת כאירוע) |
| Gemini, Ollama כגיבוי | LLM | מודל הסוכן |

Flask **לא** מאוחסן ב-Somee (Somee לא מריץ Python על hosting חינמי).
