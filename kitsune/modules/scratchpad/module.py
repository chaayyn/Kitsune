"""
kitsune.modules.scratchpad.module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Scratchpad Module.
Fast floating notepad with auto-save for ephemeral notes and snippets.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu

from kitsune.core.module import BaseModule
from kitsune.modules.scratchpad.ui import ScratchpadWindow
from kitsune.ui.icons import IconManager

if TYPE_CHECKING:
    from kitsune.core.app import KitsuneApp


class ScratchpadModule(BaseModule):
    def __init__(self, app: KitsuneApp) -> None:
        super().__init__(app)
        data_dir = Path(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))) / "kitsune"
        self._note_path = data_dir / "scratchpad.txt"
        self._window: Optional[ScratchpadWindow] = None

    @property
    def id(self) -> str:
        return "scratchpad"

    @property
    def name(self) -> str:
        return "Scratchpad"

    @property
    def description(self) -> str:
        return "Bloc-notes éphémère flottant avec sauvegarde automatique locale."

    @property
    def category(self) -> str:
        return "clipboard"

    @property
    def icon_name(self) -> str:
        return "accessories-text-editor"

    @property
    def config(self) -> Dict[str, Any]:
        return self._config

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "stay_on_top": True,
        }

    def on_disable(self) -> None:
        if self._window is not None:
            self._window.close()
            self._window = None

    def show_scratchpad(self) -> None:
        if self._window is None:
            self._window = ScratchpadWindow(self, self._note_path)
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def get_status_summary(self) -> str:
        return "Actif" if self.is_enabled else "Désactivé"

    def get_tray_actions(self, parent_menu: QMenu) -> List[QAction | QMenu]:
        if not self.is_enabled:
            return []

        act = QAction("📝 Bloc-notes (Scratchpad)...", parent_menu)
        act.setIcon(IconManager.get_icon("accessories-text-editor", fallback_color="#0ea5e9", fallback_symbol="📝"))
        act.triggered.connect(self.show_scratchpad)
        return [act]
