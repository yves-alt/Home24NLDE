import sqlite3
import os
from pathlib import Path
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "database/localization.db")


def get_db_path() -> str:
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


@contextmanager
def get_connection():
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_stats() -> dict:
    with get_connection() as conn:
        tm_count = conn.execute("SELECT COUNT(*) FROM translation_memory").fetchone()[0]
        glossary_count = conn.execute("SELECT COUNT(*) FROM glossary WHERE active=1").fetchone()[0]
        export_count = conn.execute("SELECT COUNT(*) FROM export_log").fetchone()[0]
        qa_count = conn.execute("SELECT COUNT(*) FROM qa_log").fetchone()[0]
        return {
            "tm_entries": tm_count,
            "glossary_terms": glossary_count,
            "files_exported": export_count,
            "qa_corrections": qa_count,
        }
