"""Client D-Bus asynchrone du démon, basé sur Gio.

Gio plutôt que QtDBus : PySide6 démarshalle mal les ``a{sv}`` / ``aa{sv}`` /
``v`` de l'API, alors que Gio les convertit directement en types Python. Sous
Linux, la boucle d'évènements de Qt est une boucle GLib : les rappels Gio sont
donc traités sans thread ni minuterie (voir :func:`saturn.ui.app.ensure_glib_dispatch`).

Ce module ne dépend pas de Qt, ce qui le rend testable seul.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from gi.repository import Gio, GLib

from saturn import BUS_NAME, INTERFACE, OBJECT_PATH

log = logging.getLogger(__name__)

CALL_TIMEOUT_MS = 10_000


@dataclass(frozen=True)
class CallError:
    """Erreur renvoyée par le démon (``name`` vaut par ex. ``org.saturn.Error.InvalidSetting``)."""

    name: str
    message: str

    @property
    def short_name(self) -> str:
        return self.name.rsplit(".", 1)[-1]


ResultCallback = Callable[[Any], None]
ErrorCallback = Callable[[CallError], None]


class DaemonClient:
    """Suit la présence de ``saturnd`` sur le bus et relaie ses signaux."""

    def __init__(self, connection: Gio.DBusConnection) -> None:
        self.connection = connection
        self.available = False
        self.on_available_changed: Callable[[bool], None] | None = None
        self.on_module_changed: Callable[[str, dict[str, Any]], None] | None = None
        self.on_setting_changed: Callable[[str, str, Any], None] | None = None
        self.on_module_event: Callable[[str, str, dict[str, Any]], None] | None = None

        self._watch_id = Gio.bus_watch_name_on_connection(
            connection,
            BUS_NAME,
            Gio.BusNameWatcherFlags.NONE,
            self._on_name_appeared,
            self._on_name_vanished,
        )
        self._subscription_id = connection.signal_subscribe(
            BUS_NAME,
            INTERFACE,
            None,
            OBJECT_PATH,
            None,
            Gio.DBusSignalFlags.NONE,
            self._on_signal,
        )

    @classmethod
    def for_session_bus(cls) -> DaemonClient:
        return cls(Gio.bus_get_sync(Gio.BusType.SESSION, None))

    def close(self) -> None:
        if self._watch_id:
            Gio.bus_unwatch_name(self._watch_id)
            self._watch_id = 0
        if self._subscription_id:
            self.connection.signal_unsubscribe(self._subscription_id)
            self._subscription_id = 0

    # -- appels ------------------------------------------------------------------------

    def call(
        self,
        method: str,
        args: GLib.Variant | None = None,
        on_result: ResultCallback | None = None,
        on_error: ErrorCallback | None = None,
        interface: str = INTERFACE,
    ) -> None:
        """Appel asynchrone ; ``on_result`` reçoit la réponse déjà convertie en Python."""

        def done(connection: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
            try:
                reply = connection.call_finish(result)
            except GLib.Error as exc:
                error = _to_call_error(exc)
                log.warning("%s a échoué : %s (%s)", method, error.message, error.name)
                if on_error is not None:
                    on_error(error)
                return
            if on_result is not None:
                values = reply.unpack() if reply is not None else ()
                on_result(values[0] if len(values) == 1 else values)

        self.connection.call(
            BUS_NAME,
            OBJECT_PATH,
            interface,
            method,
            args,
            None,
            Gio.DBusCallFlags.NO_AUTO_START,
            CALL_TIMEOUT_MS,
            None,
            done,
        )

    def list_modules(self, on_result: ResultCallback, on_error: ErrorCallback | None = None) -> None:
        self.call("ListModules", None, on_result, on_error)

    def get_environment(self, on_result: ResultCallback, on_error: ErrorCallback | None = None) -> None:
        self.call("GetEnvironment", None, on_result, on_error)

    def get_version(self, on_result: ResultCallback, on_error: ErrorCallback | None = None) -> None:
        self.call(
            "Get",
            GLib.Variant("(ss)", (INTERFACE, "Version")),
            on_result,
            on_error,
            interface="org.freedesktop.DBus.Properties",
        )

    def set_module_enabled(
        self,
        module_id: str,
        enabled: bool,
        on_result: ResultCallback | None = None,
        on_error: ErrorCallback | None = None,
    ) -> None:
        self.call(
            "SetModuleEnabled", GLib.Variant("(sb)", (module_id, enabled)), on_result, on_error
        )

    def get_settings_schema(
        self, module_id: str, on_result: ResultCallback, on_error: ErrorCallback | None = None
    ) -> None:
        self.call("GetSettingsSchema", GLib.Variant("(s)", (module_id,)), on_result, on_error)

    def get_settings(
        self, module_id: str, on_result: ResultCallback, on_error: ErrorCallback | None = None
    ) -> None:
        self.call("GetSettings", GLib.Variant("(s)", (module_id,)), on_result, on_error)

    def set_setting(
        self,
        module_id: str,
        key: str,
        signature: str,
        value: Any,
        on_result: ResultCallback | None = None,
        on_error: ErrorCallback | None = None,
    ) -> None:
        """``signature`` est celle du schéma (``b``, ``x``, ``d``, ``s``, ``as``)."""
        variant = GLib.Variant(signature, value)
        self.call(
            "SetSetting", GLib.Variant("(ssv)", (module_id, key, variant)), on_result, on_error
        )

    def reset_setting(
        self,
        module_id: str,
        key: str,
        on_result: ResultCallback | None = None,
        on_error: ErrorCallback | None = None,
    ) -> None:
        self.call("ResetSetting", GLib.Variant("(ss)", (module_id, key)), on_result, on_error)

    # -- présence et signaux ------------------------------------------------------------

    def _on_name_appeared(self, _connection: Any, _name: str, _owner: str) -> None:
        self._set_available(True)

    def _on_name_vanished(self, _connection: Any, _name: str) -> None:
        self._set_available(False)

    def _set_available(self, available: bool) -> None:
        if available == self.available:
            return
        self.available = available
        if self.on_available_changed is not None:
            self.on_available_changed(available)

    def _on_signal(
        self,
        _connection: Any,
        _sender: str,
        _path: str,
        _interface: str,
        signal: str,
        parameters: GLib.Variant,
    ) -> None:
        args = parameters.unpack()
        if signal == "ModuleStateChanged" and self.on_module_changed is not None:
            self.on_module_changed(*args)
        elif signal == "SettingChanged" and self.on_setting_changed is not None:
            self.on_setting_changed(*args)
        elif signal == "ModuleEvent" and self.on_module_event is not None:
            self.on_module_event(*args)


def _to_call_error(exc: GLib.Error) -> CallError:
    name = Gio.DBusError.get_remote_error(exc) or "org.saturn.Error.Failed"
    Gio.DBusError.strip_remote_error(exc)
    return CallError(name, exc.message)
