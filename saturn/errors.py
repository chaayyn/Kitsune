"""Erreurs du démon, chacune associée à un nom d'erreur D-Bus."""

from __future__ import annotations


class SaturnError(Exception):
    """Erreur de base. ``dbus_name`` est renvoyé tel quel aux clients D-Bus."""

    dbus_name = "org.saturn.Error.Failed"


class UnknownModuleError(SaturnError):
    dbus_name = "org.saturn.Error.UnknownModule"

    def __init__(self, module_id: str) -> None:
        super().__init__(f"Module inconnu : {module_id!r}")
        self.module_id = module_id


class ModuleUnavailableError(SaturnError):
    dbus_name = "org.saturn.Error.ModuleUnavailable"


class ModuleNotRunningError(SaturnError):
    dbus_name = "org.saturn.Error.ModuleNotRunning"


class UnknownSettingError(SaturnError):
    dbus_name = "org.saturn.Error.UnknownSetting"


class InvalidSettingError(SaturnError):
    dbus_name = "org.saturn.Error.InvalidSetting"


class UnknownActionError(SaturnError):
    dbus_name = "org.saturn.Error.UnknownAction"


class ActionError(SaturnError):
    """Levée par un module quand une action reçoit des paramètres invalides."""

    dbus_name = "org.saturn.Error.InvalidArgs"


class ManifestError(SaturnError):
    dbus_name = "org.saturn.Error.InvalidManifest"
