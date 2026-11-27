"""Historique du presse-papiers dans SQLite ; les images sont des fichiers à part."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from saturn import paths
from saturn.modules.clipboard.content import ClipContent

SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    preview TEXT NOT NULL DEFAULT '',
    mime TEXT NOT NULL DEFAULT '',
    image TEXT NOT NULL DEFAULT '',
    files TEXT NOT NULL DEFAULT '[]',
    digest TEXT NOT NULL UNIQUE,
    size INTEGER NOT NULL DEFAULT 0,
    pinned INTEGER NOT NULL DEFAULT 0,
    created REAL NOT NULL,
    used REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS entries_order ON entries (pinned DESC, used DESC);
"""

_IMAGE_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/gif": "gif", "image/bmp": "bmp"}


@dataclass(frozen=True)
class AddResult:
    id: int
    new: bool


class ClipboardStore:
    def __init__(self, connection: sqlite3.Connection, images_dir: Path) -> None:
        self.db = connection
        self.images_dir = images_dir
        self.db.executescript(SCHEMA)
        self.db.commit()

    # -- écriture ----------------------------------------------------------------

    def add(self, content: ClipContent, now: float | None = None) -> AddResult:
        """Ajoute une copie. Une copie déjà connue remonte simplement en tête."""
        now = time.time() if now is None else now
        digest = content.digest
        row = self.db.execute("SELECT id FROM entries WHERE digest = ?", (digest,)).fetchone()
        if row is not None:
            self.db.execute("UPDATE entries SET used = ? WHERE id = ?", (now, row["id"]))
            self.db.commit()
            return AddResult(row["id"], False)

        image_name = ""
        if content.kind == "image":
            image_name = f"{digest[:32]}.{_IMAGE_EXTENSIONS.get(content.mime, 'img')}"
            path = paths.ensure_dir(self.images_dir) / image_name
            path.write_bytes(content.image)
            path.chmod(0o600)

        cursor = self.db.execute(
            "INSERT INTO entries (kind, text, preview, mime, image, files, digest, size, created, used)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                content.kind,
                content.text,
                content.preview,
                content.mime,
                image_name,
                json.dumps(list(content.files)),
                digest,
                content.size,
                now,
                now,
            ),
        )
        self.db.commit()
        return AddResult(int(cursor.lastrowid), True)

    def touch(self, entry_id: int, now: float | None = None) -> None:
        self.db.execute("UPDATE entries SET used = ? WHERE id = ?", (time.time() if now is None else now, entry_id))
        self.db.commit()

    def set_pinned(self, entry_id: int, pinned: bool) -> bool:
        cursor = self.db.execute("UPDATE entries SET pinned = ? WHERE id = ?", (int(pinned), entry_id))
        self.db.commit()
        return cursor.rowcount > 0

    def delete(self, entry_id: int) -> bool:
        return self._delete_where("id = ?", (entry_id,)) > 0

    def clear(self, keep_pinned: bool = True) -> int:
        return self._delete_where("pinned = 0" if keep_pinned else "1", ())

    def prune(self, max_items: int, max_age_days: int, now: float | None = None) -> int:
        """Retire les entrées en trop ou trop vieilles. Les favoris sont toujours gardés."""
        now = time.time() if now is None else now
        removed = 0
        if max_age_days > 0:
            removed += self._delete_where("pinned = 0 AND used < ?", (now - max_age_days * 86400,))
        removed += self._delete_where(
            "pinned = 0 AND id NOT IN (SELECT id FROM entries WHERE pinned = 0 ORDER BY used DESC LIMIT ?)",
            (max_items,),
        )
        return removed

    # -- lecture -------------------------------------------------------------------

    def get(self, entry_id: int) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        return self._entry(row, full=True) if row else None

    def content(self, entry_id: int) -> ClipContent | None:
        row = self.db.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            return None
        if row["kind"] == "image":
            path = self.images_dir / row["image"]
            if not path.exists():
                return None
            return ClipContent("image", image=path.read_bytes(), mime=row["mime"])
        if row["kind"] == "files":
            return ClipContent("files", files=tuple(json.loads(row["files"])), mime=row["mime"])
        return ClipContent("text", text=row["text"], mime=row["mime"])

    def search(self, query: str = "", limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        """Favoris d'abord, puis du plus récent au plus ancien."""
        where, params = "1", []
        query = query.strip()
        if query:
            where = "(instr(lower(text), lower(?)) > 0 OR instr(lower(preview), lower(?)) > 0)"
            params = [query, query]
        total = self.db.execute(f"SELECT count(*) FROM entries WHERE {where}", params).fetchone()[0]
        rows = self.db.execute(
            f"SELECT * FROM entries WHERE {where} ORDER BY pinned DESC, used DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return [self._entry(row) for row in rows], int(total)

    def count(self) -> int:
        return int(self.db.execute("SELECT count(*) FROM entries").fetchone()[0])

    # -- interne ---------------------------------------------------------------------

    def _delete_where(self, where: str, params: tuple[Any, ...]) -> int:
        images = [
            row["image"]
            for row in self.db.execute(f"SELECT image FROM entries WHERE {where} AND image != ''", params)
        ]
        cursor = self.db.execute(f"DELETE FROM entries WHERE {where}", params)
        self.db.commit()
        for name in images:
            (self.images_dir / name).unlink(missing_ok=True)
        return cursor.rowcount

    def _entry(self, row: sqlite3.Row, full: bool = False) -> dict[str, Any]:
        text = row["text"]
        entry: dict[str, Any] = {
            "id": row["id"],
            "kind": row["kind"],
            "preview": row["preview"],
            # Les listes n'ont besoin que d'un extrait ; l'aperçu complet passe par « get ».
            "text": text if full else text[:2000],
            "mime": row["mime"],
            "image": str(self.images_dir / row["image"]) if row["image"] else "",
            "files": json.loads(row["files"]),
            "size": row["size"],
            "pinned": bool(row["pinned"]),
            "created": row["created"],
            "used": row["used"],
        }
        return entry
