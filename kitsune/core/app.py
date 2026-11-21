"""
kitsune.core.app
~~~~~~~~~~~~~~~~~~
Core application instance for Kitsune.
Coordinates configuration, environment detection, modules, and system tray.
"""

from __future__ import annotations
import os
import sys
from pathlib import Path
from typing import Optional
from PyQt6.QtWidgets import QApplication

from kitsune.core.config import ConfigManager
from kitsune.core.env import Environment
from kitsune.core.manager import ModuleManager
from kitsune.ui.tray import KitsuneTrayIcon
from kitsune.ui.settings import SettingsWindow
from kitsune.ui.theme import DARK_STYLESHEET


class KitsuneApp(QApplication):
    def __init__(self, argv: list[str]) -> None:
        super().__init__(argv)
        self.setApplicationName("Kitsune")
        self.setApplicationDisplayName("Kitsune")
        self.setQuitOnLastWindowClosed(False)
        self.setStyleSheet(DARK_STYLESHEET)

        # Core subsystems
        self.env = Environment.get()
        self.config_manager = ConfigManager.get()
        self.module_manager = ModuleManager(self)

        # UI windows
        self._settings_window: Optional[SettingsWindow] = None

        # Discover & initialize modules
        self.module_manager.discover_modules()
        self.module_manager.initialize_modules()

        # System tray icon
        self.tray_icon = KitsuneTrayIcon(self)
        self.tray_icon.show()

        # Listen to module updates to refresh tray menu
        self.module_manager.modules_changed.connect(self.tray_icon.rebuild_menu)

    def show_settings(self) -> None:
        if self._settings_window is None:
            self._settings_window = SettingsWindow(self)
        self._settings_window.show()
        self._settings_window.raise_()
        self._settings_window.activateWindow()

    def is_autostart_enabled(self) -> bool:
        autostart_file = Path.home() / ".config" / "autostart" / "kitsune.desktop"
        return autostart_file.exists()

    def set_autostart(self, enabled: bool) -> None:
        autostart_dir = Path.home() / ".config" / "autostart"
        autostart_file = autostart_dir / "kitsune.desktop"

        if enabled:
            autostart_dir.mkdir(parents=True, exist_ok=True)
            script_path = Path(__file__).resolve().parent.parent.parent / "run.py"
            content = f"""[Desktop Entry]
Type=Application
Name=Kitsune
Comment=Modular local-first system utility tray
Exec={sys.executable} {script_path}
Icon=accessories-character-map
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
"""
            autostart_file.write_text(content, encoding="utf-8")
        else:
            if autostart_file.exists():
                try:
                    autostart_file.unlink()
                except Exception:
                    pass

    def quit_application(self) -> None:
        self.module_manager.shutdown()
        self.quit()
