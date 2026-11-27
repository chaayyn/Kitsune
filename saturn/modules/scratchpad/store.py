"""Notes du bloc-notes dans SQLite (logique pure, sans E/S hors de la base)."""

from __future__ import annotations

import re
import sqlite3
import time
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY,
    body TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    created REAL NOT NULL,
    updated REAL NOT NULL
);
"""

MAX_BODY_CHARS = 1_000_000
UNTITLED = "Sans titre"
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+")


def note_title(body: str) -> str:
    """Titre d'une note : sa première ligne non vide, sans marque de titre Markdown."""
    for line in body.splitlines():
        line = _HEADING.sub("", line).strip()
        if line:
            return line[:60]
    return UNTITLED


def note_preview(body: str) -> str:
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    return " ".join(lines[1:])[:160]


def safe_filename(title: str) -> str:
    """Nom de fichier lisible et sans caractère piégeux."""
    name = re.sub(r"[^\w\s.-]", "", title, flags=re.UNICODE).strip().replace(" ", "-")
    name = re.sub(r"-{2,}", "-", name).strip(".-")
    return (name or "note")[:80]


class NotesStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.db = connection
        self.db.executescript(SCHEMA)
        self.db.commit()

    def create(self, body: str = "", now: float | None = None) -> int:
        now = time.time() if now is None else now
        position = self.db.execute("SELECT coalesce(max(position), -1) + 1 FROM notes").fetchone()[0]
        cursor = self.db.execute(
            "INSERT INTO notes (body, position, created, updated) VALUES (?, ?, ?, ?)",
            (body[:MAX_BODY_CHARS], position, now, now),
        )
        self.db.commit()
        return int(cursor.lastrowid)

    def save(self, note_id: int, body: str, now: float | None = None) -> bool:
        if len(body) > MAX_BODY_CHARS:
            raise ValueError("Note trop longue")
        cursor = self.db.execute(
            "UPDATE notes SET body = ?, updated = ? WHERE id = ? AND body != ?",
            (body, time.time() if now is None else now, note_id, body),
        )
        self.db.commit()
        return cursor.rowcount > 0

    def delete(self, note_id: int) -> bool:
        cursor = self.db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        self.db.commit()
        return cursor.rowcount > 0

    def move(self, note_id: int, position: int) -> None:
        """Place la note à ``position`` (0 = premier onglet) et renumérote les autres."""
        ids = [row["id"] for row in self.db.execute("SELECT id FROM notes ORDER BY position, id")]
        if note_id not in ids:
            return
        ids.remove(note_id)
        ids.insert(max(0, min(position, len(ids))), note_id)
        self.db.executemany("UPDATE notes SET position = ? WHERE id = ?", [(i, nid) for i, nid in enumerate(ids)])
        self.db.commit()

    def get(self, note_id: int) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        return self._note(row, with_body=True) if row else None

    def list(self) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM notes ORDER BY position, id").fetchall()
        return [self._note(row) for row in rows]

    def count(self) -> int:
        return int(self.db.execute("SELECT count(*) FROM notes").fetchone()[0])

    @staticmethod
    def _note(row: sqlite3.Row, with_body: bool = False) -> dict[str, Any]:
        body = row["body"]
        note: dict[str, Any] = {
            "id": row["id"],
            "title": note_title(body),
            "preview": note_preview(body),
            "words": len(body.split()),
            "created": row["created"],
            "updated": row["updated"],
        }
        if with_body:
            note["body"] = body
        return note
