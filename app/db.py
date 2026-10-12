import sqlite3
import time
from contextlib import contextmanager
from urllib.parse import urlparse, unquote

_database_url = "sqlite:///fitscreen.db"


SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    must_have_skills TEXT NOT NULL,
    nice_to_have_skills TEXT NOT NULL,
    min_years INTEGER NOT NULL,
    location TEXT NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    applicant_count INTEGER NOT NULL DEFAULT 0,
    opened_at TEXT
);
CREATE TABLE IF NOT EXISTS applications (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    status TEXT NOT NULL,
    cv_path TEXT,
    cv_text TEXT,
    agent_score INTEGER,
    agent_report_json TEXT,
    decision_reason TEXT,
    UNIQUE(job_id, candidate_id)
);
"""


def init_db(database_url: str):
    global _database_url
    _database_url = database_url
    if database_url.startswith("sqlite"):
        with connection() as conn:
            conn.executescript(SCHEMA_SQLITE)
            conn.commit()
    else:
        _init_mssql(database_url)


def _sqlite_path(url: str) -> str:
    if url.startswith("sqlite:///"):
        return url.replace("sqlite:///", "", 1)
    return "fitscreen.db"


def _init_mssql(url: str):
    import pymssql

    conn = _mssql_connect(url)
    cur = conn.cursor()
    statements = [
        """IF OBJECT_ID('events','U') IS NULL CREATE TABLE events (
            event_id VARCHAR(64) PRIMARY KEY,
            event_type VARCHAR(128) NOT NULL,
            aggregate_type VARCHAR(64) NOT NULL,
            aggregate_id VARCHAR(64) NOT NULL,
            version INT NOT NULL,
            payload_json NVARCHAR(MAX) NOT NULL,
            metadata_json NVARCHAR(MAX) NOT NULL,
            occurred_at VARCHAR(40) NOT NULL
        )""",
        """IF OBJECT_ID('users','U') IS NULL CREATE TABLE users (
            id VARCHAR(64) PRIMARY KEY,
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            full_name NVARCHAR(255) NOT NULL,
            role VARCHAR(32) NOT NULL
        )""",
        """IF OBJECT_ID('jobs','U') IS NULL CREATE TABLE jobs (
            id VARCHAR(64) PRIMARY KEY,
            title NVARCHAR(255) NOT NULL,
            description NVARCHAR(MAX) NOT NULL,
            must_have_skills NVARCHAR(MAX) NOT NULL,
            nice_to_have_skills NVARCHAR(MAX) NOT NULL,
            min_years INT NOT NULL,
            location NVARCHAR(255) NOT NULL,
            status VARCHAR(32) NOT NULL,
            created_by VARCHAR(64) NOT NULL,
            applicant_count INT NOT NULL DEFAULT 0,
            opened_at VARCHAR(40) NULL
        )""",
        """IF OBJECT_ID('applications','U') IS NULL CREATE TABLE applications (
            id VARCHAR(64) PRIMARY KEY,
            job_id VARCHAR(64) NOT NULL,
            candidate_id VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL,
            cv_path NVARCHAR(512) NULL,
            cv_text NVARCHAR(MAX) NULL,
            agent_score INT NULL,
            agent_report_json NVARCHAR(MAX) NULL,
            decision_reason NVARCHAR(MAX) NULL
        )""",
    ]
    for sql in statements:
        cur.execute(sql)
    conn.commit()
    conn.close()


def _mssql_connect(url: str):
    import pymssql

    parsed = urlparse(url.replace("mssql+pymssql://", "http://", 1))
    user = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    host = parsed.hostname or "localhost"
    port = parsed.port or 1433
    database = (parsed.path or "/").lstrip("/")
    # Somee's free tier sometimes drops the first TDS handshake ("Unexpected EOF").
    for attempt in range(3):
        try:
            return pymssql.connect(
                server=host,
                user=user,
                password=password,
                database=database,
                port=port,
                login_timeout=15,
                timeout=30,
                charset="UTF-8",
            )
        except pymssql.OperationalError:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def backend_name() -> str:
    return "sqlite" if _database_url.startswith("sqlite") else "mssql"


def describe_target() -> str:
    if _database_url.startswith("sqlite"):
        return _sqlite_path(_database_url)
    parsed = urlparse(_database_url.replace("mssql+pymssql://", "http://", 1))
    return f"{parsed.hostname}:{parsed.port or 1433}/{(parsed.path or '/').lstrip('/')}"


def ping() -> dict:
    counts = {}
    for table in ("events", "users", "jobs", "applications"):
        row = fetch_one(f"SELECT COUNT(*) AS n FROM {table}")
        counts[table] = int(row["n"]) if row else 0
    return counts


@contextmanager
def connection():
    if _database_url.startswith("sqlite"):
        conn = sqlite3.connect(_sqlite_path(_database_url), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
        finally:
            conn.close()
    else:
        conn = _mssql_connect(_database_url)
        conn.autocommit(False)
        try:
            yield conn
        finally:
            conn.close()


def execute(sql: str, params=()):
    sql = _adapt_sql(sql)
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        return cur.lastrowid if _database_url.startswith("sqlite") else None


def fetch_all(sql: str, params=()):
    sql = _adapt_sql(sql)
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        if _database_url.startswith("sqlite"):
            return [dict(r) for r in rows]
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in rows]


def fetch_one(sql: str, params=()):
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def _adapt_sql(sql: str) -> str:
    if _database_url.startswith("sqlite"):
        return sql
    return sql.replace("?", "%s")
