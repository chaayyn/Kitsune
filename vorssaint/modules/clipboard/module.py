"""
vorssaint.modules.clipboard.module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Clipboard History Module.
Locally stores clipboard history in SQLite and offers quick search and paste.
"""

from __future__ import annotations
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from PyQt6.QtGui import QAction, QClipboard
from PyQt6.QtWidgets import QMenu

from vorssaint.core.module import BaseModule
from vorssaint.modules.clipboard.storage import ClipboardStorage
from vorssaint.modules.clipboard.ui import ClipboardWindow
from vorssaint.ui.icons import IconManager

if TYPE_CHECKING:
    from vorssaint.core.app import VorssaintApp


# Regex for likely secrets/tokens/keys to avoid saving in history
SENSITIVE_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----"),
    re.compile(r"ghp_[0-9a-zA-Z]{36}"),             # GitHub PAT
    re.compile(r"glpat-[0-9a-zA-Z_-]{20}"),          # GitLab PAT
    re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,48}"),   # Slack token
    re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}"), # JWT
]


class ClipboardModule(BaseModule):
    def __init__(self, app: VorssaintApp) -> None:
        super().__init__(app)
        self.storage = ClipboardStorage()
        self._window: Optional[ClipboardWindow] = None
        self._last_content: Optional[str] = None

    @property
    def id(self) -> str:
        return "clipboard"

    @property
    def name(self) -> str:
        return "Historique Presse-papiers"

    @property
    def description(self) -> str:
        return "Historique local chiffré/sécurisé du presse-papiers avec recherche rapide."

    @property
    def category(self) -> str:
        return "clipboard"

    @property
    def icon_name(self) -> str:
        return "edit-paste"

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "history_limit": 100,
            "ignore_passwords": True,
        }

    def on_enable(self) -> None:
        clipboard = self.app.clipboard()
        clipboard.dataChanged.connect(self._on_clipboard_changed)

    def on_disable(self) -> None:
        try:
            clipboard = self.app.clipboard()
            clipboard.dataChanged.disconnect(self._on_clipboard_changed)
        except Exception:
            pass
        if self._window is not None:
            self._window.close()
            self._window = None

    def _is_sensitive(self, text: str) -> bool:
        """Heuristic check to prevent saving passwords or secret keys in history."""
        if not self._config.get("ignore_passwords", True):
            return False
        for pattern in SENSITIVE_PATTERNS:
            if pattern.search(text):
                return True
        return False

    def _on_clipboard_changed(self) -> None:
        if not self.is_enabled:
            return

        clipboard = self.app.clipboard()
        text = clipboard.text(QClipboard.Mode.Clipboard)
        if not text or text == self._last_content:
            return

        if self._is_sensitive(text):
            return

        self._last_content = text
        limit = self._config.get("history_limit", 100)
        self.storage.add_entry(text, limit=limit)
        self.state_changed.emit()

    def show_history_window(self) -> None:
        if self._window is None:
            self._window = ClipboardWindow(self)
            self._window.item_selected.connect(self._on_item_restored)

        self._window.refresh_list()
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def _on_item_restored(self, content: str) -> None:
        self._last_content = content
        clipboard = self.app.clipboard()
        clipboard.setText(content, QClipboard.Mode.Clipboard)
        self.app.env.send_notification("Presse-papiers", "Élément copié dans le presse-papiers.")

    def get_status_summary(self) -> str:
        if not self.is_enabled:
            return "Désactivé"
        count = len(self.storage.get_recent(limit=100))
        return f"Actif ({count} éléments)"

    def get_tray_actions(self, parent_menu: QMenu) -> List[QAction | QMenu]:
        if not self.is_enabled:
            return []

        menu = QMenu("📋 Presse-papiers", parent_menu)
        menu.setIcon(IconManager.get_icon("edit-paste", fallback_color="#8b5cf6", fallback_symbol="📋"))

        open_act = QAction("Ouvrir l'historique...", menu)
        open_act.triggered.connect(self.show_history_window)
        menu.addAction(open_act)
        menu.addSeparator()

        # Display last 5 recent items in submenu
        recent = self.storage.get_recent(limit=5)
        if recent:
            for _, content, _ in recent:
                clean_preview = " ".join(content.split())
                if len(clean_preview) > 35:
                    clean_preview = clean_preview[:35] + "..."
                item_act = QAction(f"📄 {clean_preview}", menu)
                item_act.triggered.connect(lambda chk, c=content: self._on_item_restored(c))
                menu.addAction(item_act)
        else:
            empty_act = QAction("(Aucun élément récent)", menu)
            empty_act.setEnabled(False)
            menu.addAction(empty_act)

        menu.addSeparator()
        clear_act = QAction("Vider l'historique", menu)
        clear_act.triggered.connect(self.storage.clear)
        menu.addAction(clear_act)

        return [menu]
