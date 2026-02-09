from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    parent_task_id TEXT,
    depth INTEGER NOT NULL,
    engine TEXT NOT NULL,
    status TEXT NOT NULL,
    goal TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    engine TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    summary_path TEXT,
    artifacts_dir TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);

CREATE TABLE IF NOT EXISTS questions (
    question_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    answered_at TEXT,
    answer TEXT,
    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
);
"""


@dataclass(frozen=True)
class TaskRecord:
    task_id: str
    parent_task_id: Optional[str]
    depth: int
    engine: str
    status: str
    goal: Optional[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    task_id: str
    engine: str
    status: str
    started_at: str
    ended_at: Optional[str]
    summary_path: Optional[str]
    artifacts_dir: Optional[str]


def init_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)


def insert_task(conn: sqlite3.Connection, record: TaskRecord) -> None:
    conn.execute(
        """
        INSERT INTO tasks (task_id, parent_task_id, depth, engine, status, goal, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.task_id,
            record.parent_task_id,
            record.depth,
            record.engine,
            record.status,
            record.goal,
            record.created_at,
            record.updated_at,
        ),
    )


def update_task_status(conn: sqlite3.Connection, task_id: str, status: str, updated_at: str) -> None:
    conn.execute(
        "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?",
        (status, updated_at, task_id),
    )


def insert_session(conn: sqlite3.Connection, record: SessionRecord) -> None:
    conn.execute(
        """
        INSERT INTO sessions (session_id, task_id, engine, status, started_at, ended_at, summary_path, artifacts_dir)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.session_id,
            record.task_id,
            record.engine,
            record.status,
            record.started_at,
            record.ended_at,
            record.summary_path,
            record.artifacts_dir,
        ),
    )


def update_session_status(
    conn: sqlite3.Connection,
    session_id: str,
    status: str,
    ended_at: Optional[str],
    summary_path: Optional[str],
) -> None:
    conn.execute(
        """
        UPDATE sessions
        SET status = ?, ended_at = ?, summary_path = ?
        WHERE session_id = ?
        """,
        (status, ended_at, summary_path, session_id),
    )


def list_tasks(conn: sqlite3.Connection) -> Iterable[TaskRecord]:
    rows = conn.execute(
        "SELECT task_id, parent_task_id, depth, engine, status, goal, created_at, updated_at FROM tasks"
    ).fetchall()
    for row in rows:
        yield TaskRecord(*row)
