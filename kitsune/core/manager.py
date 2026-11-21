"""
kitsune.core.manager
~~~~~~~~~~~~~~~~~~~~~~
Module manager that discovers, instantiates, and controls module lifecycles.
"""

from __future__ import annotations
import importlib
import pkgutil
from typing import TYPE_CHECKING, Dict, List, Optional, Type
from PyQt6.QtCore import QObject, pyqtSignal

from kitsune.core.module import BaseModule
import kitsune.modules

if TYPE_CHECKING:
    from kitsune.core.app import KitsuneApp


class ModuleManager(QObject):
    """
    Central orchestrator for all Kitsune modular plugins.
    Handles discovery, instantiation, toggling, and notifications.
    """

    modules_changed = pyqtSignal()
    module_state_updated = pyqtSignal(str)  # module_id

    def __init__(self, app: KitsuneApp) -> None:
        super().__init__()
        self.app = app
        self._registry: Dict[str, Type[BaseModule]] = {}
        self._instances: Dict[str, BaseModule] = {}

    def register_module_class(self, module_cls: Type[BaseModule]) -> None:
        """Explicitly registers a module class."""
        # Instantiate temporarily to get metadata or inspect attributes
        instance = module_cls(self.app)
        mod_id = instance.id
        self._registry[mod_id] = module_cls
        self._instances[mod_id] = instance
        instance.state_changed.connect(lambda mid=mod_id: self._on_module_state_changed(mid))

    def discover_modules(self) -> None:
        """Auto-discovers and imports all modules in the kitsune.modules package."""
        package = kitsune.modules
        for _, modname, ispkg in pkgutil.iter_modules(package.__path__):
            if ispkg:
                try:
                    module_mod = importlib.import_module(f"kitsune.modules.{modname}.module")
                    for attr_name in dir(module_mod):
                        attr = getattr(module_mod, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, BaseModule)
                            and attr is not BaseModule
                        ):
                            self.register_module_class(attr)
                except Exception as e:
                    print(f"[ModuleManager] Failed to load module {modname}: {e}")

    def initialize_modules(self) -> None:
        """Initializes all registered modules from saved user config."""
        config_mgr = self.app.config_manager
        for mod_id, instance in self._instances.items():
            mod_conf = config_mgr.get_module_config(mod_id, instance.default_config())
            instance.initialize(mod_conf)
            if mod_conf.get("enabled", True):
                supported, reason = instance.is_supported()
                if supported:
                    instance.enable()
                else:
                    print(f"[ModuleManager] Module '{mod_id}' skipped: {reason}")

    def enable_module(self, module_id: str) -> bool:
        instance = self._instances.get(module_id)
        if not instance:
            return False
        supported, reason = instance.is_supported()
        if not supported:
            return False
        instance.enable()
        self.app.config_manager.set_module_enabled(module_id, True)
        self.modules_changed.emit()
        return True

    def disable_module(self, module_id: str) -> bool:
        instance = self._instances.get(module_id)
        if not instance:
            return False
        instance.disable()
        self.app.config_manager.set_module_enabled(module_id, False)
        self.modules_changed.emit()
        return True

    def toggle_module(self, module_id: str) -> bool:
        instance = self._instances.get(module_id)
        if not instance:
            return False
        if instance.is_enabled:
            return self.disable_module(module_id)
        else:
            return self.enable_module(module_id)

    def get_module(self, module_id: str) -> Optional[BaseModule]:
        return self._instances.get(module_id)

    def get_all_modules(self) -> List[BaseModule]:
        return list(self._instances.values())

    def get_enabled_modules(self) -> List[BaseModule]:
        return [m for m in self._instances.values() if m.is_enabled]

    def _on_module_state_changed(self, module_id: str) -> None:
        self.module_state_updated.emit(module_id)
        self.modules_changed.emit()

    def shutdown(self) -> None:
        """Gracefully disables all modules on exit."""
        for instance in self._instances.values():
            if instance.is_enabled:
                try:
                    instance.disable()
                except Exception as e:
                    print(f"[ModuleManager] Error disabling {instance.id}: {e}")
