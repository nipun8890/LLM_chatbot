import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  metadata TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  system_prompt TEXT,
  created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    conn = sqlite3.connect(settings.database_path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    path = Path(settings.database_path)
    if path.parent and str(path.parent) not in ("", "."):
        path.parent.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)


def db_ok() -> bool:
    try:
        with connect() as c:
            c.execute("SELECT 1")
        return True
    except Exception:
        return False


def get_history(session_id: str) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            "SELECT role, content, metadata FROM messages WHERE session_id=? ORDER BY id", (session_id,)
        ).fetchall()
    out = []
    for r in rows:
        m = {"role": r["role"], "content": r["content"]}
        if r["role"] == "assistant" and r["metadata"]:
            m["metadata"] = json.loads(r["metadata"])
        out.append(m)
    return out


def get_system_prompt(session_id: str) -> str | None:
    with connect() as c:
        row = c.execute("SELECT system_prompt FROM sessions WHERE session_id=?", (session_id,)).fetchone()
    return row["system_prompt"] if row else None


def save_exchange(session_id: str, system_prompt: str | None, user_msg: str, reply: str, metadata: dict) -> None:
    """Persist user+assistant messages atomically; called only after a successful LLM answer."""
    now = _now()
    with connect() as c:
        c.execute(
            "INSERT INTO sessions(session_id, system_prompt, created_at) VALUES(?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET system_prompt=COALESCE(excluded.system_prompt, sessions.system_prompt)",
            (session_id, system_prompt, now),
        )
        c.execute(
            "INSERT INTO messages(session_id, role, content, metadata, created_at) VALUES(?,?,?,?,?)",
            (session_id, "user", user_msg, None, now),
        )
        c.execute(
            "INSERT INTO messages(session_id, role, content, metadata, created_at) VALUES(?,?,?,?,?)",
            (session_id, "assistant", reply, json.dumps(metadata), _now()),
        )
