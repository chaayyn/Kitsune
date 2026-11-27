"""Thème de l'interface : couleurs, polices, durées d'animation.

Exposé au QML sous le nom ``Theme``. Les durées tombent à zéro quand le bureau
demande moins d'animations (GNOME ``enable-animations``, ou
``SATURN_REDUCED_MOTION=1``).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from gi.repository import Gio
from PySide6.QtCore import Property, QObject, Signal
from PySide6.QtGui import QColor, QFontDatabase, QGuiApplication, QPalette

log = logging.getLogger(__name__)

DISPLAY_FONTS = ("Space Grotesk", "Adwaita Sans", "Cantarell", "DejaVu Sans")
MONO_FONTS = ("JetBrains Mono", "Fira Code", "Hack", "DejaVu Sans Mono")

_GNOME_INTERFACE = "org.gnome.desktop.interface"


def load_bundled_fonts(directory: Path) -> list[str]:
    """Charge les polices livrées avec l'appli (``assets/fonts``)."""
    families: list[str] = []
    if not directory.is_dir():
        return families
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in {".ttf", ".otf"}:
            continue
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            log.warning("Police illisible : %s", path)
            continue
        families += QFontDatabase.applicationFontFamilies(font_id)
    return families


def apply_palette(app: QGuiApplication) -> None:
    """Couleur des liens de l'appli : le rendu Markdown du QML lit la palette globale."""
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.Link, QColor(Theme._COLORS["accent"]))
    palette.setColor(QPalette.ColorRole.LinkVisited, QColor(Theme._COLORS["accentHover"]))
    app.setPalette(palette)


def pick_family(
    preferred: tuple[str, ...], available: set[str], override: str | None = None
) -> str:
    """Première famille disponible. ``override`` (variable d'environnement) passe devant."""
    candidates = ((override,) if override else ()) + preferred
    for family in candidates:
        if family in available:
            return family
    return preferred[-1]


class Theme(QObject):
    reducedMotionChanged = Signal()

    # Palette courte : fond, texte, un accent (anneaux de Saturne), une couleur d'alerte.
    _COLORS = {
        "background": "#0B0B0C",
        "surface": "#111113",
        "surfaceRaised": "#18181B",
        "surfaceHover": "#1F1F23",
        "text": "#F2EFE8",
        "textMuted": "#8D8A84",
        "textFaint": "#5A5853",
        "border": "#1AFFFFFF",  # rgba(255,255,255,0.10)
        "borderStrong": "#33FFFFFF",  # rgba(255,255,255,0.20)
        "accent": "#E8B44A",
        "accentHover": "#F3C566",
        "danger": "#FF6A55",
    }

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        families = set(QFontDatabase.families())
        # SATURN_DISPLAY_FONT / SATURN_MONO_FONT imposent une autre famille installée.
        self._display = pick_family(DISPLAY_FONTS, families, os.environ.get("SATURN_DISPLAY_FONT"))
        self._mono = pick_family(MONO_FONTS, families, os.environ.get("SATURN_MONO_FONT"))
        self.missing_fonts = [
            name
            for name, chosen in (("Space Grotesk", self._display), ("JetBrains Mono", self._mono))
            if chosen != name
        ]
        self._reduced_motion = False
        self._gsettings: Gio.Settings | None = None
        self._watch_reduced_motion()

    # -- mouvement -------------------------------------------------------------------

    def _watch_reduced_motion(self) -> None:
        forced = os.environ.get("SATURN_REDUCED_MOTION")
        if forced is not None:
            self._reduced_motion = forced not in {"", "0", "false"}
            return
        source = Gio.SettingsSchemaSource.get_default()
        if source is None or source.lookup(_GNOME_INTERFACE, True) is None:
            return
        self._gsettings = Gio.Settings.new(_GNOME_INTERFACE)
        self._gsettings.connect("changed::enable-animations", lambda *_: self._sync_gsettings())
        self._sync_gsettings()

    def _sync_gsettings(self) -> None:
        assert self._gsettings is not None
        reduced = not self._gsettings.get_boolean("enable-animations")
        if reduced != self._reduced_motion:
            self._reduced_motion = reduced
            self.reducedMotionChanged.emit()

    @Property(bool, notify=reducedMotionChanged)
    def reducedMotion(self) -> bool:
        return self._reduced_motion

    def _duration(self, value: int) -> int:
        return 0 if self._reduced_motion else value

    @Property(int, notify=reducedMotionChanged)
    def durationFast(self) -> int:
        return self._duration(200)

    @Property(int, notify=reducedMotionChanged)
    def durationBase(self) -> int:
        return self._duration(320)

    @Property(int, notify=reducedMotionChanged)
    def durationSlow(self) -> int:
        return self._duration(450)

    # -- polices -------------------------------------------------------------------

    @Property(str, constant=True)
    def displayFont(self) -> str:
        return self._display

    @Property(str, constant=True)
    def monoFont(self) -> str:
        return self._mono

    # -- couleurs (constantes, lues par le QML) ---------------------------------------

    background = Property(str, lambda self: Theme._COLORS["background"], constant=True)
    surface = Property(str, lambda self: Theme._COLORS["surface"], constant=True)
    surfaceRaised = Property(str, lambda self: Theme._COLORS["surfaceRaised"], constant=True)
    surfaceHover = Property(str, lambda self: Theme._COLORS["surfaceHover"], constant=True)
    text = Property(str, lambda self: Theme._COLORS["text"], constant=True)
    textMuted = Property(str, lambda self: Theme._COLORS["textMuted"], constant=True)
    textFaint = Property(str, lambda self: Theme._COLORS["textFaint"], constant=True)
    border = Property(str, lambda self: Theme._COLORS["border"], constant=True)
    borderStrong = Property(str, lambda self: Theme._COLORS["borderStrong"], constant=True)
    accent = Property(str, lambda self: Theme._COLORS["accent"], constant=True)
    accentHover = Property(str, lambda self: Theme._COLORS["accentHover"], constant=True)
    danger = Property(str, lambda self: Theme._COLORS["danger"], constant=True)
