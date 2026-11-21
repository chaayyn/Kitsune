"""
kitsune.modules.cleaning_mode.module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Cleaning Mode Module.
Temporarily locks keyboard and mouse input behind a safe full-screen overlay
allowing the user to clean their physical keyboard and screen without unwanted input.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu

from kitsune.core.module import BaseModule
from kitsune.modules.cleaning_mode.ui import CleaningLockOverlay
from kitsune.ui.icons import IconManager

if TYPE_CHECKING:
    from kitsune.core.app import KitsuneApp


class CleaningModeModule(BaseModule):
    def __init__(self, app: KitsuneApp) -> None:
        super().__init__(app)
        self._overlay: Optional[CleaningLockOverlay] = None

    @property
    def id(self) -> str:
        return "cleaning_mode"

    @property
    def name(self) -> str:
        return "Mode Nettoyage"

    @property
    def description(self) -> str:
        return "Verrouille temporairement le clavier et l'écran pour les nettoyer sans risque."

    @property
    def category(self) -> str:
        return "system"

    @property
    def icon_name(self) -> str:
        return "input-keyboard"

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "unlock_hold_seconds": 3,
        }

    def on_disable(self) -> None:
        if self._overlay is not None:
            self._overlay.close()
            self._overlay = None

    def start_cleaning_mode(self) -> None:
        if self._overlay is None:
            self._overlay = CleaningLockOverlay(self)
        self._overlay.showFullScreen()
        self.state_changed.emit()

    def on_unlocked(self) -> None:
        self._overlay = None
        self.app.env.send_notification("Mode Nettoyage", "Clavier et écran déverrouillés.")
        self.state_changed.emit()

    def get_status_summary(self) -> str:
        return "Actif" if self.is_enabled else "Désactivé"

    def get_tray_actions(self, parent_menu: QMenu) -> List[QAction | QMenu]:
        if not self.is_enabled:
            return []

        act = QAction("✨ Mode Nettoyage (Verrouiller)...", parent_menu)
        act.setIcon(IconManager.get_icon("input-keyboard", fallback_color="#f97316", fallback_symbol="✨"))
        act.triggered.connect(self.start_cleaning_mode)
        return [act]
