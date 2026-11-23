
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(
    os.getenv(
        "LOAN_DB",
        str(Path(__file__).resolve().parent / "loans.db"),
    )
)


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                equipment_id INTEGER NOT NULL,
                start_date TEXT NOT NULL,
                end_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK(status IN ('active', 'cancelled')),
                CHECK(start_date <= end_date)
            )
        """)
        conn.execute("""
           CREATE TABLE IF NOT EXISTS equipment_deletion_guards (
           equipment_id INTEGER PRIMARY KEY,
            status TEXT NOT NULL
            CHECK(status IN ('pending', 'deleted')),
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)


def rows(sql, params=()):
    with db() as conn:
        return [
            dict(row)
            for row in conn.execute(sql, params).fetchall()
        ]
