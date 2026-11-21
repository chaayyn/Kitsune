"""
kitsune.core.env
~~~~~~~~~~~~~~~~~~
Environment detection (Wayland / X11 / Desktop Environment / Available System Tools).
Provides clean diagnostic checks and graceful fallbacks.
"""

from __future__ import annotations
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional, Dict


@dataclass
class SystemCapabilities:
    session_type: str            # 'wayland', 'x11', or 'unknown'
    desktop_environment: str     # 'gnome', 'kde', 'hyprland', 'sway', 'xfce', etc.
    has_systemd_inhibit: bool
    has_wpctl: bool
    has_pactl: bool
    has_gdbus: bool
    has_notify_send: bool
    has_wl_clipboard: bool
    has_xclip: bool


class Environment:
    _instance: Optional[Environment] = None

    def __init__(self) -> None:
        self.session_type = self._detect_session_type()
        self.desktop_environment = self._detect_desktop_environment()
        self._tools_cache: Dict[str, bool] = {}

    @classmethod
    def get(cls) -> Environment:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def _detect_session_type() -> str:
        session = os.environ.get("XDG_SESSION_TYPE", "").lower()
        if session in ("wayland", "x11"):
            return session
        if "WAYLAND_DISPLAY" in os.environ:
            return "wayland"
        if "DISPLAY" in os.environ:
            return "x11"
        return "unknown"

    @staticmethod
    def _detect_desktop_environment() -> str:
        de = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
        if not de:
            de = os.environ.get("DESKTOP_SESSION", "").lower()
        # Normalization
        if "gnome" in de:
            return "gnome"
        elif "kde" in de or "plasma" in de:
            return "kde"
        elif "hyprland" in de:
            return "hyprland"
        elif "sway" in de:
            return "sway"
        elif "xfce" in de:
            return "xfce"
        return de or "generic"

    def is_wayland(self) -> bool:
        return self.session_type == "wayland"

    def is_x11(self) -> bool:
        return self.session_type == "x11"

    def has_tool(self, tool_name: str) -> bool:
        if tool_name not in self._tools_cache:
            self._tools_cache[tool_name] = shutil.which(tool_name) is not None
        return self._tools_cache[tool_name]

    def get_capabilities(self) -> SystemCapabilities:
        return SystemCapabilities(
            session_type=self.session_type,
            desktop_environment=self.desktop_environment,
            has_systemd_inhibit=self.has_tool("systemd-inhibit"),
            has_wpctl=self.has_tool("wpctl"),
            has_pactl=self.has_tool("pactl"),
            has_gdbus=self.has_tool("gdbus"),
            has_notify_send=self.has_tool("notify-send"),
            has_wl_clipboard=self.has_tool("wl-copy") and self.has_tool("wl-paste"),
            has_xclip=self.has_tool("xclip"),
        )

    def send_notification(self, title: str, message: str, app_name: str = "Kitsune", icon: str = "dialog-information") -> None:
        """Sends a desktop notification using notify-send or prints fallback."""
        if self.has_tool("notify-send"):
            try:
                subprocess.Popen(
                    ["notify-send", "-a", app_name, "-i", icon, title, message],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return
            except Exception:
                pass
        print(f"[{app_name}] {title}: {message}")
