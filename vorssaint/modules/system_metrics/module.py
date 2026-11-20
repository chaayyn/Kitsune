"""
vorssaint.modules.system_metrics.module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Lightweight System Metrics Module.
Directly reads /proc/stat and /proc/meminfo with zero external dependencies.
Displays CPU, RAM, and system uptime in the tray menu.
"""

from __future__ import annotations
import os
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu

from vorssaint.core.module import BaseModule
from vorssaint.ui.icons import IconManager

if TYPE_CHECKING:
    from vorssaint.core.app import VorssaintApp


class SystemMetricsModule(BaseModule):
    def __init__(self, app: VorssaintApp) -> None:
        super().__init__(app)
        self._prev_idle: int = 0
        self._prev_total: int = 0
        self._cpu_usage: float = 0.0
        self._ram_usage: float = 0.0
        self._ram_total_gb: float = 0.0
        self._ram_used_gb: float = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(2000)  # Every 2 seconds
        self._timer.timeout.connect(self._update_metrics)

    @property
    def id(self) -> str:
        return "system_metrics"

    @property
    def name(self) -> str:
        return "Métriques Système"

    @property
    def description(self) -> str:
        return "Aperçu léger en direct de l'utilisation CPU et RAM (lecture directe /proc)."

    @property
    def category(self) -> str:
        return "system"

    @property
    def icon_name(self) -> str:
        return "utilities-system-monitor"

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": False,
            "refresh_interval_seconds": 2,
        }

    def on_enable(self) -> None:
        self._update_metrics()
        self._timer.start()

    def on_disable(self) -> None:
        self._timer.stop()

    def _update_metrics(self) -> None:
        try:
            # Read CPU from /proc/stat
            with open("/proc/stat", "r") as f:
                cpu_line = f.readline()
                parts = [int(p) for p in cpu_line.split()[1:8]]
                idle = parts[3] + parts[4]
                total = sum(parts)

                if self._prev_total > 0:
                    delta_total = total - self._prev_total
                    delta_idle = idle - self._prev_idle
                    if delta_total > 0:
                        self._cpu_usage = max(0.0, min(100.0, (1.0 - (delta_idle / delta_total)) * 100.0))

                self._prev_idle = idle
                self._prev_total = total

            # Read RAM from /proc/meminfo
            meminfo: Dict[str, int] = {}
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = int(parts[1].split()[0])  # kB
                        meminfo[key] = val

            total_kb = meminfo.get("MemTotal", 0)
            avail_kb = meminfo.get("MemAvailable", 0)
            if total_kb > 0:
                used_kb = total_kb - avail_kb
                self._ram_total_gb = total_kb / (1024 * 1024)
                self._ram_used_gb = used_kb / (1024 * 1024)
                self._ram_usage = (used_kb / total_kb) * 100.0

            self.state_changed.emit()
        except Exception:
            pass

    def get_status_summary(self) -> str:
        if not self.is_enabled:
            return "Désactivé"
        return f"CPU: {self._cpu_usage:.1f}% | RAM: {self._ram_usage:.1f}%"

    def get_tray_actions(self, parent_menu: QMenu) -> List[QAction | QMenu]:
        if not self.is_enabled:
            return []

        menu = QMenu(f"📊 Système (CPU {self._cpu_usage:.0f}% • RAM {self._ram_usage:.0f}%)", parent_menu)
        menu.setIcon(IconManager.get_icon("utilities-system-monitor", fallback_color="#06b6d4", fallback_symbol="📊"))

        cpu_act = QAction(f"⚡ CPU : {self._cpu_usage:.1f}%", menu)
        cpu_act.setEnabled(False)
        menu.addAction(cpu_act)

        ram_act = QAction(f"💾 RAM : {self._ram_used_gb:.1f} Go / {self._ram_total_gb:.1f} Go ({self._ram_usage:.1f}%)", menu)
        ram_act.setEnabled(False)
        menu.addAction(ram_act)

        return [menu]
