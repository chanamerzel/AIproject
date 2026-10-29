import sqlite3
import threading
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
CREATE UNIQUE INDEX IF NOT EXISTS ux_events_aggregate_version
    ON events(aggregate_id, version);
CREATE INDEX IF NOT EXISTS ix_events_type ON events(event_type);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL,
    auth_provider TEXT NOT NULL DEFAULT 'password'
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
CREATE INDEX IF NOT EXISTS ix_applications_job ON applications(job_id);
CREATE INDEX IF NOT EXISTS ix_applications_candidate ON applications(candidate_id);
CREATE INDEX IF NOT EXISTS ix_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS ix_jobs_status ON jobs(status);
"""


def init_db(database_url: str):
    global _database_url
    _database_url = database_url
    if database_url.startswith("sqlite"):
        with connection() as conn:
            conn.executescript(SCHEMA_SQLITE)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
            if "auth_provider" not in columns:
                conn.execute("ALTER TABLE users ADD COLUMN auth_provider TEXT NOT NULL DEFAULT 'password'")
            conn.commit()
    else:
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                _init_mssql(database_url)
                return
            except Exception as exc:
                last_error = exc
                time.sleep(2 * (attempt + 1))
        raise last_error


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
            role VARCHAR(32) NOT NULL,
            auth_provider VARCHAR(16) NOT NULL DEFAULT 'password'
        )""",
        """IF COL_LENGTH('users', 'auth_provider') IS NULL
            ALTER TABLE users ADD auth_provider VARCHAR(16) NOT NULL DEFAULT 'password'""",
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
    _mssql_indexes = (
        ("ux_events_agg_ver", "events", "CREATE UNIQUE INDEX ux_events_agg_ver ON events(aggregate_id, version)"),
        ("ix_events_type", "events", "CREATE INDEX ix_events_type ON events(event_type)"),
        ("ix_applications_job", "applications", "CREATE INDEX ix_applications_job ON applications(job_id)"),
        ("ix_applications_candidate", "applications", "CREATE INDEX ix_applications_candidate ON applications(candidate_id)"),
        ("ix_applications_status", "applications", "CREATE INDEX ix_applications_status ON applications(status)"),
        ("ix_jobs_status", "jobs", "CREATE INDEX ix_jobs_status ON jobs(status)"),
    )
    for name, table, ddl in _mssql_indexes:
        try:
            cur.execute(
                f"""IF NOT EXISTS (
                    SELECT 1 FROM sys.indexes
                    WHERE name = '{name}' AND object_id = OBJECT_ID('{table}')
                )
                {ddl}"""
            )
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                raise
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


class _DbState(threading.local):
    def __init__(self):
        self.conn = None
        self.in_tx = False
        self.request_bound = False


_state = _DbState()


_idle = []
_idle_lock = threading.Lock()
_MAX_IDLE = 4


def bind():
    """Hold one connection for this request so a page does not reconnect on every query."""
    if _state.conn is None:
        _state.conn = _borrow()
        _state.request_bound = True


def release():
    if not _state.request_bound:
        return
    conn = _state.conn
    in_tx = _state.in_tx
    _state.conn = None
    _state.request_bound = False
    _state.in_tx = False
    if conn is None:
        return
    try:
        if in_tx:
            conn.rollback()
    except Exception:
        _close_quietly(conn)
        return
    _give_back(conn)


def is_version_conflict(exc: Exception) -> bool:
    text = str(exc).lower()
    if "ux_events" in text:
        return True
    return "version" in text and ("unique" in text or "duplicate" in text)


def ping() -> dict:
    row = fetch_one(
        """SELECT
            (SELECT COUNT(*) FROM events) AS events,
            (SELECT COUNT(*) FROM users) AS users,
            (SELECT COUNT(*) FROM jobs) AS jobs,
            (SELECT COUNT(*) FROM applications) AS applications"""
    )
    names = ("events", "users", "jobs", "applications")
    if not row:
        return {name: 0 for name in names}
    return {name: int(row[name]) for name in names}


def _close_quietly(conn):
    try:
        conn.close()
    except Exception:
        pass


def _borrow():
    if _database_url.startswith("sqlite"):
        return _open()
    with _idle_lock:
        while _idle:
            conn = _idle.pop()
            try:
                conn.cursor().execute("SELECT 1")
                return conn
            except Exception:
                _close_quietly(conn)
    return _open()


def _give_back(conn):
    if _database_url.startswith("sqlite"):
        _close_quietly(conn)
        return
    with _idle_lock:
        if len(_idle) < _MAX_IDLE:
            _idle.append(conn)
            return
    _close_quietly(conn)


_wal_ready: set[str] = set()


def _open():
    if _database_url.startswith("sqlite"):
        path = _sqlite_path(_database_url)
        conn = sqlite3.connect(path, timeout=30)
        conn.row_factory = sqlite3.Row
        # WAL is stored on the database file, so later connections inherit it.
        if path not in _wal_ready:
            conn.execute("PRAGMA journal_mode=WAL")
            _wal_ready.add(path)
        conn.execute("PRAGMA cache_size=-8000")
        conn.execute("PRAGMA temp_store=MEMORY")
        return conn
    conn = _mssql_connect(_database_url)
    conn.autocommit(False)
    return conn


@contextmanager
def hold_connection():
    """Keep one connection for a batch of queries when a request has not already bound one."""
    if _state.conn is not None:
        yield
        return
    _state.conn = _borrow()
    _state.request_bound = True
    try:
        yield
    finally:
        release()


@contextmanager
def connection():
    if _state.conn is not None:
        yield _state.conn
        return
    conn = _open()
    _state.conn = conn
    try:
        yield conn
    finally:
        _state.conn = None
        conn.close()


@contextmanager
def transaction():
    """Commit an event and its projection together, or roll both back."""
    if _state.in_tx:
        yield
        return
    with connection() as conn:
        _state.in_tx = True
        try:
            yield
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            _state.in_tx = False


def execute(sql: str, params=()):
    sql = _adapt_sql(sql)
    with connection() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        if not _state.in_tx:
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
