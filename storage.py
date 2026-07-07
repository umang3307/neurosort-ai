"""
storage.py
----------
Persistence layer for NeuroSort AI.

This is the "memory" component of the agent (Course Day 3: Context
Engineering — Sessions, Skills & Memory). Every triage decision the agent
makes is written to a local SQLite database, so the app remembers a user's
history across restarts instead of forgetting everything after each run.

Using SQLite (instead of an in-memory list) is a deliberate choice: it's
zero-config, ships with Python, and gives us real durability without
requiring the user to stand up external infrastructure for a demo project.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "neurosort.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't already exist. Safe to call every run."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,          -- do_now | schedule | delegate | archive
                content TEXT NOT NULL,
                detail TEXT,                     -- extra structured info (time, recipient, etc.)
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open'  -- open | done | archived
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_input TEXT NOT NULL,
                cognitive_load_score INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )


def add_task(category: str, content: str, detail: str = "") -> int:
    """Persist a single triaged task. Returns the new row id."""
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO tasks (category, content, detail, created_at) VALUES (?, ?, ?, ?)",
            (category, content, detail, datetime.now(timezone.utc).isoformat()),
        )
        return cur.lastrowid


def update_task_status(task_id: int, status: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (status, task_id))


def get_open_tasks(category: str | None = None) -> list[sqlite3.Row]:
    with _connect() as conn:
        if category:
            cur = conn.execute(
                "SELECT * FROM tasks WHERE status = 'open' AND category = ? ORDER BY created_at DESC",
                (category,),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM tasks WHERE status = 'open' ORDER BY created_at DESC"
            )
        return cur.fetchall()


def get_history(limit: int = 20) -> list[sqlite3.Row]:
    with _connect() as conn:
        cur = conn.execute(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return cur.fetchall()


def log_session(raw_input: str, cognitive_load_score: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO session_log (raw_input, cognitive_load_score, created_at) VALUES (?, ?, ?)",
            (raw_input, cognitive_load_score, datetime.now(timezone.utc).isoformat()),
        )


def get_stats() -> dict:
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM tasks").fetchone()["c"]
        by_cat = conn.execute(
            "SELECT category, COUNT(*) AS c FROM tasks GROUP BY category"
        ).fetchall()
        avg_load = conn.execute(
            "SELECT AVG(cognitive_load_score) AS avg FROM session_log"
        ).fetchone()["avg"]
        return {
            "total_tasks": total,
            "by_category": {row["category"]: row["c"] for row in by_cat},
            "avg_cognitive_load": round(avg_load, 1) if avg_load else None,
        }
