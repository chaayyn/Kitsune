"""
kitsune.modules.keep_awake.module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Keep Awake Module for Linux.
Prevents system sleep, screen dimming, and screen saver idle timeout
using systemd-inhibit and org.freedesktop.ScreenSaver D-Bus.
"""

from __future__ import annotations
import subprocess
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QMenu

from kitsune.core.module import BaseModule
from kitsune.ui.icons import IconManager

if TYPE_CHECKING:
    from kitsune.core.app import KitsuneApp


class KeepAwakeModule(BaseModule):
    def __init__(self, app: KitsuneApp) -> None:
        super().__init__(app)
        self._process: Optional[subprocess.Popen] = None
        self._target_end_time: Optional[float] = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_timer)
        self._duration_minutes: int = 0  # 0 means infinite

    @property
    def id(self) -> str:
        return "keep_awake"

    @property
    def name(self) -> str:
        return "Keep Awake"

    @property
    def description(self) -> str:
        return "Empêche la mise en veille et l'extinction de l'écran (temporaire ou indéfini)."

    @property
    def category(self) -> str:
        return "energy"

    @property
    def icon_name(self) -> str:
        return "preferences-system-power"

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "default_duration_minutes": 0,
            "notify_on_change": True,
        }

    def is_supported(self) -> Tuple[bool, str]:
        env = self.app.env
        if env.has_tool("systemd-inhibit"):
            return True, "Supporté via systemd-inhibit"
        if env.has_tool("gdbus"):
            return True, "Supporté via D-Bus gdbus"
        return False, "Nécessite 'systemd-inhibit' ou 'gdbus'"

    def on_enable(self) -> None:
        # Activated as a module, ready to be engaged
        pass

    def on_disable(self) -> None:
        self.deactivate_keep_awake()

    def is_active(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def activate_keep_awake(self, duration_minutes: int = 0) -> bool:
        """
        Activates sleep prevention.
        duration_minutes: 0 for indefinite, >0 for timed duration.
        """
        self.deactivate_keep_awake()
        self._duration_minutes = duration_minutes

        try:
            # Spawn systemd-inhibit holding sleep infinity
            cmd = [
                "systemd-inhibit",
                "--what=idle:sleep:handle-lid-switch",
                "--who=Kitsune",
                "--why=Kitsune Keep Awake active",
                "--mode=block",
                "sleep", "infinity"
            ]
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            if duration_minutes > 0:
                self._target_end_time = time.time() + (duration_minutes * 60)
                self._timer.start(1000)  # Check every second
            else:
                self._target_end_time = None
                self._timer.stop()

            if self._config.get("notify_on_change", True):
                dur_str = f"pour {duration_minutes} min" if duration_minutes > 0 else "indéfiniment"
                self.app.env.send_notification("Keep Awake Activé", f"Mise en veille désactivée {dur_str}.")

            self.state_changed.emit()
            return True
        except Exception as e:
            print(f"[KeepAwake] Failed to start systemd-inhibit: {e}")
            self._process = None
            return False

    def deactivate_keep_awake(self) -> None:
        """Stops inhibition and restores normal power management."""
        self._timer.stop()
        self._target_end_time = None
        if self._process is not None:
            try:
                self._process.terminate()
                self._process.wait(timeout=1.0)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

            if self._config.get("notify_on_change", True) and self.is_enabled:
                self.app.env.send_notification("Keep Awake Désactivé", "Gestion de veille système restaurée.")

            self.state_changed.emit()

    def _check_timer(self) -> None:
        if self._target_end_time and time.time() >= self._target_end_time:
            self.deactivate_keep_awake()

    def get_remaining_seconds(self) -> Optional[int]:
        if self._target_end_time:
            remaining = int(self._target_end_time - time.time())
            return max(0, remaining)
        return None

    def get_status_summary(self) -> str:
        if not self.is_enabled:
            return "Désactivé"
        if not self.is_active():
            return "Inactif"
        rem = self.get_remaining_seconds()
        if rem is not None:
            mins, secs = divmod(rem, 60)
            return f"Actif ({mins}m {secs:02d}s)"
        return "Actif (Illimité)"

    def get_tray_actions(self, parent_menu: QMenu) -> List[QAction | QMenu]:
        if not self.is_enabled:
            return []

        active = self.is_active()
        status_text = self.get_status_summary()

        # Create a submenu for Keep Awake
        menu = QMenu(f"☕ Keep Awake ({status_text})", parent_menu)
        menu.setIcon(IconManager.get_icon("preferences-system-power", fallback_color="#f59e0b", fallback_symbol="⚡"))

        # Quick toggle action
        toggle_act = QAction("Désactiver" if active else "Activer (Illimité)", menu)
        toggle_act.triggered.connect(lambda: self.deactivate_keep_awake() if active else self.activate_keep_awake(0))
        menu.addAction(toggle_act)
        menu.addSeparator()

        # Preset durations
        durations = [
            ("15 minutes", 15),
            ("30 minutes", 30),
            ("1 heure", 60),
            ("2 heures", 120),
            ("Illimité", 0),
        ]
        for label, mins in durations:
            act = QAction(label, menu)
            act.triggered.connect(lambda checked, m=mins: self.activate_keep_awake(m))
            menu.addAction(act)

        return [menu]
