"""
vorssaint.modules.clipboard.storage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
SQLite storage for clipboard history with retention limits and fast search.
"""

from __future__ import annotations
import os
import sqlite3
import time
from pathlib import Path
from typing import List, Tuple, Optional


class ClipboardStorage:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            data_dir = Path(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))) / "vorssaint"
            data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = data_dir / "clipboard.sqlite3"
        else:
            self.db_path = Path(db_path)

        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS clipboard_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content TEXT NOT NULL UNIQUE,
                    created_at REAL NOT NULL,
                    character_count INTEGER NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_clipboard_created ON clipboard_history(created_at DESC)")
            conn.commit()

    def add_entry(self, content: str, limit: int = 100) -> bool:
        """Adds a new clip. If duplicate, updates its timestamp to move it to the top."""
        if not content or not content.strip():
            return False

        now = time.time()
        char_count = len(content)

        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO clipboard_history (content, created_at, character_count)
                VALUES (?, ?, ?)
                ON CONFLICT(content) DO UPDATE SET
                    created_at = excluded.created_at,
                    character_count = excluded.character_count
            """, (content, now, char_count))

            # Prune older entries beyond limit
            conn.execute("""
                DELETE FROM clipboard_history
                WHERE id NOT IN (
                    SELECT id FROM clipboard_history ORDER BY created_at DESC LIMIT ?
                )
            """, (limit,))
            conn.commit()
        return True

    def get_recent(self, limit: int = 50, search_query: str = "") -> List[Tuple[int, str, float]]:
        """Returns list of (id, content, created_at) matching query."""
        with self._get_connection() as conn:
            if search_query:
                cursor = conn.execute("""
                    SELECT id, content, created_at
                    FROM clipboard_history
                    WHERE content LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (f"%{search_query}%", limit))
            else:
                cursor = conn.execute("""
                    SELECT id, content, created_at
                    FROM clipboard_history
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
            return [(row["id"], row["content"], row["created_at"]) for row in cursor.fetchall()]

    def clear(self) -> None:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM clipboard_history")
            conn.commit()

    def delete_item(self, item_id: int) -> None:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM clipboard_history WHERE id = ?", (item_id,))
            conn.commit()
