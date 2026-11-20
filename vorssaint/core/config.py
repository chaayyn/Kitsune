"""
vorssaint.core.config
~~~~~~~~~~~~~~~~~~~~~
Persistent configuration manager for Vorssaint.
Stores configuration in ~/.config/vorssaint/config.json using atomic writes.
"""

from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Callable, List


DEFAULT_GLOBAL_CONFIG: Dict[str, Any] = {
    "theme": "dark",
    "autostart": False,
    "notifications_enabled": True,
    "modules": {
        "keep_awake": {"enabled": True, "default_duration_minutes": 0},
        "clean_url": {"enabled": True, "notify_on_clean": True},
        "clipboard": {"enabled": True, "history_limit": 100, "ignore_passwords": True},
        "audio_control": {"enabled": True, "notify_on_mute": True},
        "scratchpad": {"enabled": True, "stay_on_top": True},
        "color_picker": {"enabled": True, "default_format": "hex"},
        "cleaning_mode": {"enabled": True, "unlock_hold_seconds": 3},
        "system_metrics": {"enabled": False, "refresh_interval_seconds": 2},
    }
}


class ConfigManager:
    _instance: Optional[ConfigManager] = None

    def __init__(self, config_dir: Optional[Path] = None) -> None:
        if config_dir is None:
            xdg_config = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
            self.config_dir = Path(xdg_config) / "vorssaint"
        else:
            self.config_dir = Path(config_dir)

        self.config_file = self.config_dir / "config.json"
        self._data: Dict[str, Any] = {}
        self._change_listeners: List[Callable[[Dict[str, Any]], None]] = []
        self.load()

    @classmethod
    def get(cls) -> ConfigManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load(self) -> None:
        """Loads configuration from file or initializes defaults."""
        if not self.config_file.exists():
            self._data = dict(DEFAULT_GLOBAL_CONFIG)
            self.save()
            return

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            # Merge with defaults to ensure all keys exist
            self._data = self._deep_merge(DEFAULT_GLOBAL_CONFIG, loaded)
        except Exception as e:
            print(f"[Config] Error reading {self.config_file}: {e}. Using defaults.")
            self._data = dict(DEFAULT_GLOBAL_CONFIG)

    def save(self) -> None:
        """Atomically saves configuration to ~/.config/vorssaint/config.json."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            # Write to temporary file first, then atomic rename
            with tempfile.NamedTemporaryFile("w", dir=self.config_dir, delete=False, encoding="utf-8") as tf:
                json.dump(self._data, tf, indent=2, ensure_ascii=False)
                temp_path = tf.name
            os.replace(temp_path, self.config_file)
        except Exception as e:
            print(f"[Config] Error saving configuration: {e}")

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        result = dict(base)
        for key, val in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(val, dict):
                result[key] = self._deep_merge(result[key], val)
            else:
                result[key] = val
        return result

    def get_value(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set_value(self, key: str, value: Any, auto_save: bool = True) -> None:
        self._data[key] = value
        if auto_save:
            self.save()
            self._notify_listeners()

    def get_module_config(self, module_id: str, default_module_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        modules = self._data.setdefault("modules", {})
        if module_id not in modules:
            modules[module_id] = default_module_config or {"enabled": True}
        return modules[module_id]

    def set_module_config(self, module_id: str, config: Dict[str, Any], auto_save: bool = True) -> None:
        modules = self._data.setdefault("modules", {})
        modules[module_id] = config
        if auto_save:
            self.save()
            self._notify_listeners()

    def is_module_enabled(self, module_id: str, default: bool = True) -> bool:
        mod_conf = self.get_module_config(module_id)
        return bool(mod_conf.get("enabled", default))

    def set_module_enabled(self, module_id: str, enabled: bool) -> None:
        mod_conf = self.get_module_config(module_id)
        mod_conf["enabled"] = enabled
        self.save()
        self._notify_listeners()

    def add_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self._change_listeners.append(callback)

    def _notify_listeners(self) -> None:
        for listener in self._change_listeners:
            try:
                listener(self._data)
            except Exception as e:
                print(f"[Config] Listener error: {e}")
