"""Briques d'un module Saturn : manifeste, contexte et classe de base.

Un module est un sous-paquet de :mod:`saturn.modules` qui contient :

* ``__init__.py`` : uniquement un ``MANIFEST`` (:class:`ModuleInfo`), sans
  import lourd. Il est lu pour lister les modules, même désactivés ;
* l'implémentation (par ex. ``module.py``), désignée par
  ``ModuleInfo.entrypoint``. Elle n'est importée que si le module est activé,
  pour qu'un module désactivé ne coûte ni mémoire ni processeur.
"""

from __future__ import annotations

import importlib.util
import inspect
import logging
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, Literal

from saturn import paths
from saturn.desktop import Environment
from saturn.errors import UnknownActionError, UnknownSettingError
from saturn.settings import Setting
from saturn.storage import Database


class Category(StrEnum):
    CLIPBOARD = "clipboard"
    TOOLS = "tools"
    SYSTEM = "system"
    SOUND = "sound"
    WINDOWS = "windows"
    ENERGY = "energy"
    CAPTURE = "capture"


@dataclass(frozen=True)
class Requirement:
    """Dépendance système nécessaire au fonctionnement d'un module."""

    kind: Literal["binary", "python"]
    name: str
    #: Indication pour l'utilisateur, par ex. le paquet à installer.
    hint: str = ""

    @classmethod
    def binary(cls, name: str, hint: str = "") -> Requirement:
        return cls("binary", name, hint)

    @classmethod
    def python(cls, name: str, hint: str = "") -> Requirement:
        return cls("python", name, hint)

    def is_met(self) -> bool:
        if self.kind == "binary":
            return shutil.which(self.name) is not None
        try:
            return importlib.util.find_spec(self.name) is not None
        except (ImportError, ValueError):
            return False

    def describe(self) -> str:
        return f"{self.name} ({self.hint})" if self.hint else self.name


@dataclass(frozen=True)
class ModuleInfo:
    """Manifeste d'un module, lisible sans importer son implémentation."""

    id: str
    name: str
    description: str
    category: Category
    #: ``"<sous-module relatif>:<Classe>"``, par ex. ``".module:CleanUrlModule"``.
    entrypoint: str
    default_enabled: bool = False
    settings: tuple[Setting, ...] = ()
    requirements: tuple[Requirement, ...] = ()

    def __post_init__(self) -> None:
        if not (self.id.isidentifier() and self.id.islower()):
            raise ValueError(f"Identifiant de module invalide : {self.id!r}")
        if self.entrypoint.count(":") != 1:
            raise ValueError(f"{self.id} : entrypoint attendu sous la forme 'module:Classe'")
        keys = [setting.key for setting in self.settings]
        if len(keys) != len(set(keys)):
            raise ValueError(f"{self.id} : clés de réglages en double")

    def setting(self, key: str) -> Setting:
        for setting in self.settings:
            if setting.key == key:
                return setting
        raise UnknownSettingError(f"Le module {self.id!r} n'a pas de réglage {key!r}")

    def missing_requirements(self) -> list[Requirement]:
        return [req for req in self.requirements if not req.is_met()]


class ModuleContext:
    """Ce que le démon met à disposition d'un module en cours d'exécution."""

    def __init__(
        self,
        info: ModuleInfo,
        env: Environment,
        settings_getter: Callable[[], dict[str, Any]],
        emitter: Callable[[str, Mapping[str, Any]], None],
    ) -> None:
        self.info = info
        self.env = env
        self.log = logging.getLogger(f"saturn.modules.{info.id}")
        self._settings_getter = settings_getter
        self._emitter = emitter
        self._database: Database | None = None

    @property
    def id(self) -> str:
        return self.info.id

    @property
    def settings(self) -> dict[str, Any]:
        """Réglages effectifs (valeurs par défaut + choix de l'utilisateur)."""
        return self._settings_getter()

    def setting(self, key: str) -> Any:
        self.info.setting(key)  # lève UnknownSettingError si la clé n'existe pas
        return self._settings_getter()[key]

    @property
    def data_dir(self) -> Path:
        """Dossier de données du module (créé à la demande avec :func:`paths.ensure_dir`)."""
        return paths.data_dir() / "modules" / self.id

    def database(self) -> Database:
        """Base SQLite du module, créée au premier usage."""
        if self._database is None:
            self._database = Database(paths.data_dir() / "modules" / f"{self.id}.db")
        return self._database

    def emit(self, event: str, data: Mapping[str, Any] | None = None) -> None:
        """Diffuse un évènement aux clients (signal D-Bus ``ModuleEvent``)."""
        self._emitter(event, dict(data or {}))

    def close(self) -> None:
        if self._database is not None:
            self._database.close()


def action(name: str | None = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Expose une méthode du module comme action appelable par D-Bus.

    La méthode reçoit un ``dict`` de paramètres et renvoie un ``dict`` (ou
    ``None``). Elle peut être synchrone ou ``async``.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        func.__saturn_action__ = name or func.__name__  # type: ignore[attr-defined]
        return func

    return decorator


class Module:
    """Classe de base des modules. Toutes les méthodes sont optionnelles."""

    _actions: ClassVar[dict[str, str]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        actions: dict[str, str] = {}
        for klass in reversed(cls.__mro__):
            for attr, value in vars(klass).items():
                action_name = getattr(value, "__saturn_action__", None)
                if action_name:
                    actions[action_name] = attr
        cls._actions = actions

    def __init__(self, context: ModuleContext) -> None:
        self.ctx = context

    async def start(self) -> None:
        """Appelée à l'activation : ouvrir les ressources, lancer les tâches."""

    async def stop(self) -> None:
        """Appelée à la désactivation et à l'arrêt du démon : tout libérer."""

    def on_setting_changed(self, key: str, value: Any) -> None:
        """Appelée quand un réglage change pendant que le module tourne."""

    @classmethod
    def action_names(cls) -> list[str]:
        return sorted(cls._actions)

    async def call_action(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        attr = self._actions.get(name)
        if attr is None:
            raise UnknownActionError(f"Le module {self.ctx.id!r} n'a pas d'action {name!r}")
        result = getattr(self, attr)(params)
        if inspect.isawaitable(result):
            result = await result
        return dict(result or {})
