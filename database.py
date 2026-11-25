import os
import sqlite3
from config import Config

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None


def _is_postgres():
    return bool(os.environ.get("DATABASE_URL"))


def _adapt_query(sql):
    if _is_postgres():
        return sql.replace("?", "%s")
    return sql


class DBConnectionWrapper:
    def __init__(self, conn, is_pg):
        self._conn = conn
        self.is_pg = is_pg

    def cursor(self):
        if self.is_pg:
            cur = self._conn.cursor(cursor_factory=RealDictCursor)
        else:
            cur = self._conn.cursor()
        return DBCursorWrapper(cur, self.is_pg)

    def execute(self, sql, params=()):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


class DBCursorWrapper:
    def __init__(self, cur, is_pg):
        self._cur = cur
        self.is_pg = is_pg
        self._last_inserted_id = None

    def execute(self, sql, params=()):
        query = _adapt_query(sql)
        appended_returning = False
        if self.is_pg and query.strip().upper().startswith("INSERT") and "RETURNING" not in query.upper():
            query = f"{query.rstrip().rstrip(';')} RETURNING id"
            appended_returning = True

        self._cur.execute(query, params)

        if appended_returning:
            try:
                row = self._cur.fetchone()
                if row:
                    self._last_inserted_id = row["id"] if isinstance(row, dict) else row[0]
            except Exception:
                self._last_inserted_id = None

        return self

    def fetchone(self):
        row = self._cur.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        rows = self._cur.fetchall()
        return [dict(r) for r in rows]

    @property
    def lastrowid(self):
        if self.is_pg:
            return self._last_inserted_id
        return self._cur.lastrowid

    def close(self):
        self._cur.close()


def get_db_connection():
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        if psycopg2 is None:
            raise RuntimeError("psycopg2-binary is required when DATABASE_URL is set.")
        pg_conn = psycopg2.connect(database_url)
        return DBConnectionWrapper(pg_conn, is_pg=True)

    sqlite_conn = sqlite3.connect(Config.DATABASE_PATH, timeout=30)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_conn.execute("PRAGMA foreign_keys = ON")
    return DBConnectionWrapper(sqlite_conn, is_pg=False)


def _ensure_column_exists(cursor, is_pg, table_name, column_name, column_def):
    if is_pg:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_def}")
    else:
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = [row["name"] if isinstance(row, dict) else row[1] for row in cursor.fetchall()]
        if column_name not in cols:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if conn.is_pg:
            id_col = "SERIAL PRIMARY KEY"
            ts_col = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        else:
            id_col = "INTEGER PRIMARY KEY AUTOINCREMENT"
            ts_col = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS users (
                id {id_col},
                full_name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                avatar_url TEXT,
                course_info TEXT DEFAULT 'Alva''s College Student',
                created_at {ts_col}
            )
        """)

        _ensure_column_exists(cursor, conn.is_pg, "users", "avatar_url", "TEXT")
        _ensure_column_exists(cursor, conn.is_pg, "users", "course_info", "TEXT DEFAULT 'Alva''s College Student'")

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS resumes (
                id {id_col},
                user_id INTEGER NOT NULL,
                resume_filepath TEXT NOT NULL,
                parsed_skills TEXT,
                uploaded_at {ts_col},
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS jobs (
                id {id_col},
                posted_by INTEGER,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT NOT NULL,
                job_type TEXT DEFAULT 'Full Time',
                package_lpa TEXT,
                skills TEXT NOT NULL,
                apply_url TEXT,
                description TEXT,
                created_at {ts_col},
                FOREIGN KEY (posted_by) REFERENCES users(id) ON DELETE SET NULL
            )
        """)

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS job_actions (
                id {id_col},
                user_id INTEGER NOT NULL,
                job_key TEXT NOT NULL,
                title TEXT NOT NULL,
                company TEXT NOT NULL,
                location TEXT,
                job_type TEXT,
                skills TEXT,
                apply_url TEXT,
                match_score INTEGER DEFAULT 0,
                action_type TEXT NOT NULL,
                status TEXT DEFAULT 'Submitted',
                created_at {ts_col},
                UNIQUE(user_id, job_key, action_type),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        conn.commit()
    finally:
        cursor.close()
        conn.close()