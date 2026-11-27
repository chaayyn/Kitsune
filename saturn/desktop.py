"""Détection du bureau et du type de session.

Les modules s'en servent pour choisir le bon adaptateur : sous Wayland, ce
qu'une appli a le droit de faire dépend du compositeur (GNOME, KDE, wlroots…).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SessionType(StrEnum):
    WAYLAND = "wayland"
    X11 = "x11"
    TTY = "tty"
    UNKNOWN = "unknown"


class Desktop(StrEnum):
    GNOME = "gnome"
    KDE = "kde"
    HYPRLAND = "hyprland"
    SWAY = "sway"
    NIRI = "niri"
    WAYFIRE = "wayfire"
    RIVER = "river"
    LABWC = "labwc"
    COSMIC = "cosmic"
    XFCE = "xfce"
    CINNAMON = "cinnamon"
    MATE = "mate"
    BUDGIE = "budgie"
    LXQT = "lxqt"
    UNKNOWN = "unknown"


class Family(StrEnum):
    """Regroupe les bureaux qui exposent les mêmes protocoles.

    ``WLROOTS`` désigne les compositeurs qui implémentent les protocoles
    ``wlr-*`` / ``ext-*`` (data-control, foreign-toplevel…), même s'ils ne
    reposent pas tous sur la bibliothèque wlroots (Hyprland, niri).
    """

    GNOME = "gnome"
    KDE = "kde"
    WLROOTS = "wlroots"
    OTHER = "other"


_DESKTOP_TOKENS: dict[str, Desktop] = {
    "gnome": Desktop.GNOME,
    "gnome-classic": Desktop.GNOME,
    "gnome-flashback": Desktop.GNOME,
    "ubuntu": Desktop.GNOME,
    "pop": Desktop.GNOME,
    "kde": Desktop.KDE,
    "plasma": Desktop.KDE,
    "plasmawayland": Desktop.KDE,
    "hyprland": Desktop.HYPRLAND,
    "sway": Desktop.SWAY,
    "niri": Desktop.NIRI,
    "wayfire": Desktop.WAYFIRE,
    "river": Desktop.RIVER,
    "labwc": Desktop.LABWC,
    "wlroots": Desktop.UNKNOWN,
    "cosmic": Desktop.COSMIC,
    "xfce": Desktop.XFCE,
    "x-cinnamon": Desktop.CINNAMON,
    "cinnamon": Desktop.CINNAMON,
    "mate": Desktop.MATE,
    "budgie": Desktop.BUDGIE,
    "budgie-desktop": Desktop.BUDGIE,
    "lxqt": Desktop.LXQT,
}

# Variables propres à un compositeur, plus fiables que XDG_CURRENT_DESKTOP.
_DESKTOP_MARKERS: tuple[tuple[str, Desktop], ...] = (
    ("HYPRLAND_INSTANCE_SIGNATURE", Desktop.HYPRLAND),
    ("SWAYSOCK", Desktop.SWAY),
    ("NIRI_SOCKET", Desktop.NIRI),
)

_FAMILIES: dict[Desktop, Family] = {
    Desktop.GNOME: Family.GNOME,
    Desktop.KDE: Family.KDE,
    Desktop.HYPRLAND: Family.WLROOTS,
    Desktop.SWAY: Family.WLROOTS,
    Desktop.NIRI: Family.WLROOTS,
    Desktop.WAYFIRE: Family.WLROOTS,
    Desktop.RIVER: Family.WLROOTS,
    Desktop.LABWC: Family.WLROOTS,
}


@dataclass(frozen=True)
class Environment:
    desktop: Desktop
    family: Family
    session: SessionType
    #: Valeur brute de ``XDG_CURRENT_DESKTOP``, utile pour le diagnostic.
    raw_desktop: str = ""

    @property
    def is_wayland(self) -> bool:
        return self.session is SessionType.WAYLAND

    @property
    def is_x11(self) -> bool:
        return self.session is SessionType.X11

    def to_dict(self) -> dict[str, Any]:
        return {
            "desktop": str(self.desktop),
            "family": str(self.family),
            "session": str(self.session),
            "raw_desktop": self.raw_desktop,
        }


def detect(env: Mapping[str, str] | None = None) -> Environment:
    """Détecte le bureau courant à partir des variables d'environnement."""
    env = os.environ if env is None else env
    desktop = _detect_desktop(env)
    return Environment(
        desktop=desktop,
        family=_FAMILIES.get(desktop, Family.OTHER),
        session=_detect_session(env),
        raw_desktop=env.get("XDG_CURRENT_DESKTOP", ""),
    )


def _detect_session(env: Mapping[str, str]) -> SessionType:
    declared = env.get("XDG_SESSION_TYPE", "").strip().lower()
    if declared in {"wayland", "x11", "tty"}:
        return SessionType(declared)
    if env.get("WAYLAND_DISPLAY"):
        return SessionType.WAYLAND
    if env.get("DISPLAY"):
        return SessionType.X11
    return SessionType.UNKNOWN


def _detect_desktop(env: Mapping[str, str]) -> Desktop:
    for variable, desktop in _DESKTOP_MARKERS:
        if env.get(variable):
            return desktop

    candidates: list[str] = []
    for variable in ("XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "DESKTOP_SESSION"):
        candidates += [part.strip().lower() for part in env.get(variable, "").split(":")]

    for token in candidates:
        desktop = _DESKTOP_TOKENS.get(token)
        if desktop is not None and desktop is not Desktop.UNKNOWN:
            return desktop
    if env.get("KDE_FULL_SESSION"):
        return Desktop.KDE
    return Desktop.UNKNOWN
