"""Emplacements des fichiers selon la spécification XDG Base Directory.

Les chemins sont recalculés à chaque appel pour respecter les variables
d'environnement courantes (pratique pour les tests et les sessions isolées).
"""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "saturn"


def _xdg_dir(variable: str, fallback: str) -> Path:
    value = os.environ.get(variable, "")
    # La spécification impose d'ignorer les chemins relatifs.
    if value and os.path.isabs(value):
        return Path(value)
    return Path.home() / fallback


def config_dir() -> Path:
    """``~/.config/saturn`` : réglages de l'utilisateur."""
    return _xdg_dir("XDG_CONFIG_HOME", ".config") / APP_NAME


def data_dir() -> Path:
    """``~/.local/share/saturn`` : données persistantes (bases SQLite…)."""
    return _xdg_dir("XDG_DATA_HOME", ".local/share") / APP_NAME


def state_dir() -> Path:
    """``~/.local/state/saturn`` : état non essentiel (journaux…)."""
    return _xdg_dir("XDG_STATE_HOME", ".local/state") / APP_NAME


def cache_dir() -> Path:
    """``~/.cache/saturn`` : fichiers jetables."""
    return _xdg_dir("XDG_CACHE_HOME", ".cache") / APP_NAME


def ensure_dir(path: Path) -> Path:
    """Crée ``path`` (accès réservé à l'utilisateur) s'il n'existe pas."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path
