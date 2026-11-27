"""Cycle de vie des modules : activation, réglages, actions."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from saturn.config import Config
from saturn.desktop import Environment
from saturn.errors import InvalidSettingError, ModuleNotRunningError, ModuleUnavailableError
from saturn.module import Module, ModuleContext, ModuleInfo
from saturn.registry import Registry
from saturn.settings import Setting

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModuleState:
    info: ModuleInfo
    enabled: bool
    running: bool
    missing: tuple[str, ...]
    error: str | None
    actions: tuple[str, ...]

    @property
    def available(self) -> bool:
        return not self.missing

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.info.id,
            "name": self.info.name,
            "description": self.info.description,
            "category": str(self.info.category),
            "enabled": self.enabled,
            "running": self.running,
            "available": self.available,
            "missing": list(self.missing),
            "error": self.error or "",
            "actions": list(self.actions),
        }


StateListener = Callable[[ModuleState], None]
SettingListener = Callable[[str, Setting, Any], None]
EventListener = Callable[[str, str, dict[str, Any]], None]


class ModuleManager:
    """Démarre uniquement les modules activés et garde la config à jour."""

    def __init__(self, registry: Registry, config: Config, env: Environment) -> None:
        self.registry = registry
        self.config = config
        self.env = env
        self.state_listeners: list[StateListener] = []
        self.setting_listeners: list[SettingListener] = []
        self.event_listeners: list[EventListener] = []
        self._running: dict[str, tuple[Module, ModuleContext]] = {}
        self._errors: dict[str, str] = {}
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    # -- démarrage / arrêt du démon ---------------------------------------------

    def discover(self) -> None:
        self.registry.discover()

    async def start(self) -> None:
        """Démarre tous les modules activés (``discover`` doit avoir été appelé)."""
        for module_id in self.registry.infos:
            if self.is_enabled(module_id):
                async with self._locks[module_id]:
                    if module_id not in self._running:
                        await self._start(module_id)

    async def stop(self) -> None:
        for module_id in reversed(list(self._running)):
            async with self._locks[module_id]:
                if module_id in self._running:
                    await self._stop(module_id)

    # -- état ------------------------------------------------------------------

    def is_enabled(self, module_id: str) -> bool:
        info = self.registry.info(module_id)
        chosen = self.config.module_enabled(module_id)
        return info.default_enabled if chosen is None else chosen

    def is_running(self, module_id: str) -> bool:
        return module_id in self._running

    def state(self, module_id: str) -> ModuleState:
        info = self.registry.info(module_id)
        running = self._running.get(module_id)
        return ModuleState(
            info=info,
            enabled=self.is_enabled(module_id),
            running=running is not None,
            missing=tuple(req.describe() for req in info.missing_requirements()),
            error=self._errors.get(module_id),
            actions=tuple(running[0].action_names()) if running else (),
        )

    def states(self) -> list[ModuleState]:
        return [self.state(module_id) for module_id in self.registry.infos]

    async def set_enabled(self, module_id: str, enabled: bool) -> ModuleState:
        info = self.registry.info(module_id)
        async with self._locks[module_id]:
            if enabled:
                missing = info.missing_requirements()
                if missing:
                    raise ModuleUnavailableError(
                        f"Impossible d'activer {info.name} : il manque "
                        + ", ".join(req.describe() for req in missing)
                    )
            self.config.set_module_enabled(module_id, enabled)
            self.config.save()
            if enabled and module_id not in self._running:
                await self._start(module_id)
            elif not enabled:
                if module_id in self._running:
                    await self._stop(module_id)
                self._errors.pop(module_id, None)
        state = self.state(module_id)
        self._notify(self.state_listeners, state)
        return state

    # -- réglages ----------------------------------------------------------------

    def settings(self, module_id: str) -> dict[str, Any]:
        """Réglages effectifs. Une valeur enregistrée invalide retombe sur le défaut."""
        info = self.registry.info(module_id)
        stored = self.config.module_settings(module_id)
        values: dict[str, Any] = {}
        for setting in info.settings:
            if setting.key in stored:
                try:
                    values[setting.key] = setting.validate(stored[setting.key])
                    continue
                except InvalidSettingError as exc:
                    log.warning("Réglage enregistré ignoré (%s), valeur par défaut utilisée", exc)
            values[setting.key] = setting.default_value()
        return values

    def set_setting(self, module_id: str, key: str, value: Any) -> Any:
        setting = self.registry.info(module_id).setting(key)
        value = setting.validate(value)
        self.config.set_module_setting(module_id, key, value)
        self.config.save()
        self._apply_setting(module_id, setting, value)
        return value

    def reset_setting(self, module_id: str, key: str) -> Any:
        setting = self.registry.info(module_id).setting(key)
        if self.config.reset_module_setting(module_id, key):
            self.config.save()
        value = setting.default_value()
        self._apply_setting(module_id, setting, value)
        return value

    # -- actions -----------------------------------------------------------------

    async def call_action(
        self, module_id: str, action: str, params: Mapping[str, Any]
    ) -> dict[str, Any]:
        info = self.registry.info(module_id)
        running = self._running.get(module_id)
        if running is None:
            raise ModuleNotRunningError(f"Le module {info.name} n'est pas actif")
        return await running[0].call_action(action, dict(params))

    # -- interne -----------------------------------------------------------------

    async def _start(self, module_id: str) -> bool:
        info = self.registry.info(module_id)
        missing = info.missing_requirements()
        if missing:
            self._errors[module_id] = "Dépendances manquantes : " + ", ".join(
                req.describe() for req in missing
            )
            log.warning("%s non démarré : %s", module_id, self._errors[module_id])
            return False

        context = ModuleContext(
            info,
            self.env,
            settings_getter=lambda: self.settings(module_id),
            emitter=lambda event, data: self._emit(module_id, event, data),
        )
        try:
            instance = self.registry.load_class(module_id)(context)
            await instance.start()
        except Exception as exc:
            log.exception("Échec du démarrage du module %s", module_id)
            self._errors[module_id] = str(exc) or type(exc).__name__
            context.close()
            return False

        self._running[module_id] = (instance, context)
        self._errors.pop(module_id, None)
        log.info("Module démarré : %s", module_id)
        return True

    async def _stop(self, module_id: str) -> None:
        instance, context = self._running.pop(module_id)
        try:
            await instance.stop()
        except Exception:
            log.exception("Erreur à l'arrêt du module %s", module_id)
        finally:
            context.close()
        log.info("Module arrêté : %s", module_id)

    def _apply_setting(self, module_id: str, setting: Setting, value: Any) -> None:
        running = self._running.get(module_id)
        if running is not None:
            try:
                running[0].on_setting_changed(setting.key, value)
            except Exception:
                log.exception("Le module %s n'a pas pu appliquer %s", module_id, setting.key)
        self._notify(self.setting_listeners, module_id, setting, value)

    def _emit(self, module_id: str, event: str, data: dict[str, Any]) -> None:
        self._notify(self.event_listeners, module_id, event, data)

    @staticmethod
    def _notify(listeners: list[Callable[..., None]], *args: Any) -> None:
        for listener in list(listeners):
            try:
                listener(*args)
            except Exception:
                log.exception("Erreur dans un abonné")
