"""Configuration persistante : modules activés et réglages modifiés.

Seules les valeurs choisies par l'utilisateur sont enregistrées ; les valeurs
par défaut viennent des manifestes des modules. Un module désinstallé garde
donc ses réglages s'il revient plus tard.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from saturn import paths

log = logging.getLogger(__name__)

CONFIG_VERSION = 1


class Config:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._modules: dict[str, dict[str, Any]] = {}

    # -- chargement / sauvegarde ------------------------------------------------

    @classmethod
    def load(cls, path: Path | None = None) -> Config:
        """Charge la configuration. Un fichier corrompu est mis de côté, jamais écrasé."""
        config = cls(path or paths.config_dir() / "config.json")
        if not config.path.exists():
            return config
        try:
            raw = json.loads(config.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("la racine doit être un objet JSON")
        except (OSError, ValueError) as exc:
            backup = config.path.with_name(f"{config.path.name}.corrupt-{int(time.time())}")
            log.warning("Configuration illisible (%s), copie conservée dans %s", exc, backup)
            try:
                config.path.replace(backup)
            except OSError:
                log.exception("Impossible de mettre de côté %s", config.path)
            return config

        modules = raw.get("modules", {})
        if isinstance(modules, dict):
            for module_id, entry in modules.items():
                if isinstance(module_id, str) and isinstance(entry, dict):
                    config._modules[module_id] = _sanitize_entry(entry)
        return config

    def save(self) -> None:
        """Écriture atomique : fichier temporaire puis renommage."""
        paths.ensure_dir(self.path.parent)
        payload = json.dumps(
            {"version": CONFIG_VERSION, "modules": self._modules},
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
        fd, tmp_name = tempfile.mkstemp(prefix=".config-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, self.path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    # -- accès ---------------------------------------------------------------

    def module_enabled(self, module_id: str) -> bool | None:
        """``None`` si l'utilisateur n'a jamais choisi (on suit alors le manifeste)."""
        value = self._modules.get(module_id, {}).get("enabled")
        return value if isinstance(value, bool) else None

    def set_module_enabled(self, module_id: str, enabled: bool) -> None:
        self._entry(module_id)["enabled"] = enabled

    def module_settings(self, module_id: str) -> dict[str, Any]:
        """Copie des réglages modifiés par l'utilisateur (non validés)."""
        return dict(self._modules.get(module_id, {}).get("settings", {}))

    def set_module_setting(self, module_id: str, key: str, value: Any) -> None:
        self._entry(module_id).setdefault("settings", {})[key] = value

    def reset_module_setting(self, module_id: str, key: str) -> bool:
        """Retire une valeur personnalisée. Renvoie ``True`` si elle existait."""
        settings = self._modules.get(module_id, {}).get("settings", {})
        return settings.pop(key, _MISSING) is not _MISSING

    def _entry(self, module_id: str) -> dict[str, Any]:
        return self._modules.setdefault(module_id, {})


_MISSING = object()


def _sanitize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    if isinstance(entry.get("enabled"), bool):
        clean["enabled"] = entry["enabled"]
    settings = entry.get("settings")
    if isinstance(settings, dict):
        clean["settings"] = {k: v for k, v in settings.items() if isinstance(k, str)}
    return clean
