"""
vorssaint.ui.tray
~~~~~~~~~~~~~~~~~
System Tray Icon and dynamic context menu.
Rebuilds cleanly whenever module states or active modules change.
"""

from __future__ import annotations
from typing import TYPE_CHECKING
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from vorssaint.ui.icons import IconManager

if TYPE_CHECKING:
    from vorssaint.core.app import VorssaintApp


class VorssaintTrayIcon(QSystemTrayIcon):
    def __init__(self, app: VorssaintApp) -> None:
        super().__init__()
        self.app = app
        self.setIcon(IconManager.get_app_icon())
        self.setToolTip("Vorssaint - Utilitaires Système Modulaires")

        self.menu = QMenu()
        self.setContextMenu(self.menu)

        self.activated.connect(self._on_tray_activated)
        self.rebuild_menu()

    def rebuild_menu(self) -> None:
        """Dynamically reconstructs the tray menu based on enabled modules."""
        self.menu.clear()

        # Header title
        header_act = QAction("⚡ Vorssaint", self.menu)
        header_act.setEnabled(False)
        self.menu.addAction(header_act)
        self.menu.addSeparator()

        # Enabled modules items
        enabled_modules = self.app.module_manager.get_enabled_modules()
        has_items = False

        for module in enabled_modules:
            try:
                actions = module.get_tray_actions(self.menu)
                if actions:
                    has_items = True
                    for act in actions:
                        if isinstance(act, QMenu):
                            self.menu.addMenu(act)
                        elif isinstance(act, QAction):
                            self.menu.addAction(act)
            except Exception as e:
                print(f"[Tray] Error adding actions for {module.id}: {e}")

        if not has_items:
            empty_act = QAction("(Aucun module actif)", self.menu)
            empty_act.setEnabled(False)
            self.menu.addAction(empty_act)

        self.menu.addSeparator()

        # Settings
        settings_act = QAction("⚙️ Paramètres & Modules...", self.menu)
        settings_act.triggered.connect(self.app.show_settings)
        self.menu.addAction(settings_act)

        self.menu.addSeparator()

        # Quit
        quit_act = QAction("Quitter Vorssaint", self.menu)
        quit_act.triggered.connect(self.app.quit_application)
        self.menu.addAction(quit_act)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Single click: show menu or settings
            self.menu.popup(self.geometry().center())
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.app.show_settings()
