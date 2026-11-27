"""Base SQLite propre à chaque module, ouverte seulement à la demande."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from saturn import paths


class Database:
    """Connexion SQLite paresseuse : aucun fichier n'est créé tant qu'on ne s'en sert pas.

    La connexion appartient au thread de la boucle du démon. Un module qui
    lance du travail dans un autre thread doit ouvrir sa propre connexion.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._connection: sqlite3.Connection | None = None

    @property
    def is_open(self) -> bool:
        return self._connection is not None

    @property
    def connection(self) -> sqlite3.Connection:
        if self._connection is None:
            paths.ensure_dir(self.path.parent)
            connection = sqlite3.connect(self.path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            self.path.chmod(0o600)
            self._connection = connection
        return self._connection

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
