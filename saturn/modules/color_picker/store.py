"""Nuancier : les dernières couleurs prélevées, sans doublon."""

from __future__ import annotations

import sqlite3
import time
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS colors (
    hex TEXT PRIMARY KEY,
    picked REAL NOT NULL
);
"""


class ColorStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.db = connection
        self.db.executescript(SCHEMA)

    def add(self, hex_value: str, keep: int, now: float | None = None) -> None:
        """Ajoute (ou remonte) une couleur, puis ne garde que les ``keep`` dernières."""
        with self.db:
            self.db.execute(
                "INSERT INTO colors (hex, picked) VALUES (?, ?) "
                "ON CONFLICT(hex) DO UPDATE SET picked = excluded.picked",
                (hex_value, time.time() if now is None else now),
            )
            self.trim(keep)

    def trim(self, keep: int) -> None:
        self.db.execute(
            "DELETE FROM colors WHERE hex NOT IN (SELECT hex FROM colors ORDER BY picked DESC LIMIT ?)",
            (keep,),
        )

    def list(self) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT hex, picked FROM colors ORDER BY picked DESC")
        return [{"hex": hex_value, "picked": picked} for hex_value, picked in rows]

    def delete(self, hex_value: str) -> bool:
        with self.db:
            return self.db.execute("DELETE FROM colors WHERE hex = ?", (hex_value,)).rowcount > 0

    def clear(self) -> None:
        with self.db:
            self.db.execute("DELETE FROM colors")
