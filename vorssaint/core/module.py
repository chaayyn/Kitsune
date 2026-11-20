"""
vorssaint.core.module
~~~~~~~~~~~~~~~~~~~~~
Base interface and lifecycle for Vorssaint modules.
Each feature (Keep Awake, Clean URL, Clipboard, Audio...) inherits from BaseModule.
"""

from __future__ import annotations
from abc import ABCMeta, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
import PyQt6.sip
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QWidget

if TYPE_CHECKING:
    from vorssaint.core.app import VorssaintApp
    from vorssaint.core.config import ConfigManager
    from vorssaint.core.env import Environment


class QABCMeta(PyQt6.sip.wrappertype, ABCMeta):
    """Metaclass resolving conflict between PyQt6 wrappertype and ABCMeta."""
    pass


class BaseModule(QObject, metaclass=QABCMeta):
    """
    Abstract base class for all Vorssaint modular plugins.
    Ensures zero resource consumption when disabled.
    """

    # Emitted when the module's state changes (to refresh tray menu or UI)
    state_changed = pyqtSignal()

    def __init__(self, app: VorssaintApp) -> None:
        super().__init__()
        self.app = app
        self._is_enabled: bool = False
        self._config: Dict[str, Any] = {}

    @property
    @abstractmethod
    def id(self) -> str:
        """Unique identifier for this module (e.g. 'keep_awake')."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable display name (e.g. 'Keep Awake')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description of the feature."""
        pass

    @property
    def category(self) -> str:
        """Category: 'clipboard', 'energy', 'audio', 'system'."""
        return "system"

    @property
    def icon_name(self) -> str:
        """Freedesktop icon name or local asset key."""
        return "application-x-executable"

    def default_config(self) -> Dict[str, Any]:
        """Default configuration dictionary for this module."""
        return {"enabled": True}

    def is_supported(self) -> Tuple[bool, str]:
        """
        Validates if system requirements for this module are met.
        Returns (is_supported, reason_if_not_supported).
        """
        return True, "Supported"

    @property
    def is_enabled(self) -> bool:
        return self._is_enabled

    def initialize(self, config: Dict[str, Any]) -> None:
        """Called once upon application startup with saved module config."""
        self._config = {**self.default_config(), **config}

    def enable(self) -> None:
        """
        Activates the module. Starts listeners, timers, hooks or D-Bus connections.
        Must be idempotent.
        """
        if self._is_enabled:
            return
        supported, reason = self.is_supported()
        if not supported:
            print(f"[{self.id}] Cannot enable: {reason}")
            return
        self._is_enabled = True
        self.on_enable()
        self.state_changed.emit()

    def disable(self) -> None:
        """
        Deactivates the module. Releases all hooks, timers, background processes.
        Zero background CPU/RAM overhead when disabled.
        Must be idempotent.
        """
        if not self._is_enabled:
            return
        self._is_enabled = False
        self.on_disable()
        self.state_changed.emit()

    def set_config(self, new_config: Dict[str, Any]) -> None:
        """Updates module configuration."""
        self._config.update(new_config)
        self.on_config_updated(self._config)

    # Hooks for subclasses to override
    def on_enable(self) -> None:
        """Override to initialize active resources."""
        pass

    def on_disable(self) -> None:
        """Override to cleanly free resources."""
        pass

    def on_config_updated(self, config: Dict[str, Any]) -> None:
        """Override if config change requires runtime adjustments."""
        pass

    def get_tray_actions(self, parent_menu: QMenu) -> List[QAction | QMenu]:
        """
        Returns QAction(s) or submenus to be inserted into the main system tray menu.
        If the module has no direct tray actions, returns empty list.
        """
        return []

    def get_settings_widget(self, parent: Optional[QWidget] = None) -> Optional[QWidget]:
        """
        Optional custom widget to configure module settings in Preferences window.
        Returns None if default settings UI suffices.
        """
        return None

    def get_status_summary(self) -> str:
        """Short status string for UI (e.g. 'Active (30m left)', 'Muted', etc.)."""
        return "Actif" if self._is_enabled else "Désactivé"
