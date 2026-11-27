"""Découverte des modules disponibles à partir de leurs manifestes."""

from __future__ import annotations

import importlib
import logging
import pkgutil

from saturn.errors import ManifestError, UnknownModuleError
from saturn.module import Module, ModuleInfo

log = logging.getLogger(__name__)

DEFAULT_PACKAGE = "saturn.modules"


class Registry:
    """Lit le ``MANIFEST`` de chaque sous-paquet sans importer l'implémentation."""

    def __init__(self, package: str = DEFAULT_PACKAGE) -> None:
        self.package = package
        self._infos: dict[str, ModuleInfo] = {}
        self._packages: dict[str, str] = {}

    def discover(self) -> dict[str, ModuleInfo]:
        self._infos.clear()
        self._packages.clear()
        root = importlib.import_module(self.package)
        for entry in sorted(pkgutil.iter_modules(root.__path__), key=lambda e: e.name):
            if not entry.ispkg or entry.name.startswith("_"):
                continue
            package_name = f"{self.package}.{entry.name}"
            try:
                info = _read_manifest(package_name)
            except Exception:
                log.exception("Module ignoré : manifeste invalide dans %s", package_name)
                continue
            if info.id in self._infos:
                log.error("Module ignoré : identifiant %r déjà utilisé (%s)", info.id, package_name)
                continue
            self._infos[info.id] = info
            self._packages[info.id] = package_name
        log.debug("Modules découverts : %s", ", ".join(self._infos) or "aucun")
        return dict(self._infos)

    @property
    def infos(self) -> dict[str, ModuleInfo]:
        return dict(self._infos)

    def info(self, module_id: str) -> ModuleInfo:
        try:
            return self._infos[module_id]
        except KeyError:
            raise UnknownModuleError(module_id) from None

    def load_class(self, module_id: str) -> type[Module]:
        """Importe l'implémentation du module (seulement quand il est activé)."""
        info = self.info(module_id)
        module_path, _, class_name = info.entrypoint.partition(":")
        python_module = importlib.import_module(module_path, self._packages[module_id])
        cls = getattr(python_module, class_name, None)
        if not (isinstance(cls, type) and issubclass(cls, Module)):
            raise ManifestError(f"{info.entrypoint} n'est pas une sous-classe de Module")
        return cls


def _read_manifest(package_name: str) -> ModuleInfo:
    package = importlib.import_module(package_name)
    info = getattr(package, "MANIFEST", None)
    if not isinstance(info, ModuleInfo):
        raise ManifestError(f"{package_name} ne définit pas de MANIFEST")
    return info
