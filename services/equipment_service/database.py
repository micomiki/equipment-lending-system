
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(
    os.environ.get(
        "EQUIPMENT_DB",
        str(Path(__file__).resolve().parent / "equipment.db"),
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
            CREATE TABLE IF NOT EXISTS equipment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT ''
            )
        """)


def rows(sql, params=()):
    with db() as conn:
        return [
            dict(row)
            for row in conn.execute(sql, params).fetchall()
        ]
