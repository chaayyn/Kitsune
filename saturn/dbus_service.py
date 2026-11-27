"""API D-Bus du démon (bus de session), implémentée avec Gio.

Exemples avec ``gdbus`` ::

    gdbus call --session -d org.saturn.Daemon -o /org/saturn/Daemon \\
        -m org.saturn.Daemon1.ListModules
    gdbus call --session -d org.saturn.Daemon -o /org/saturn/Daemon \\
        -m org.saturn.Daemon1.SetModuleEnabled clean_url false
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable, Mapping
from typing import Any

from gi.repository import Gio, GLib

from saturn import BUS_NAME, INTERFACE, OBJECT_PATH, __version__
from saturn.desktop import Environment
from saturn.errors import SaturnError
from saturn.manager import ModuleManager, ModuleState
from saturn.settings import Setting

log = logging.getLogger(__name__)

INTROSPECTION_XML = f"""
<node>
  <interface name="{INTERFACE}">
    <!-- Bureau et type de session détectés : desktop, family, session, raw_desktop. -->
    <method name="GetEnvironment">
      <arg name="environment" type="a{{sv}}" direction="out"/>
    </method>
    <!-- Chaque entrée : id, name, description, category, enabled, running,
         available, missing (as), error, actions (as). -->
    <method name="ListModules">
      <arg name="modules" type="aa{{sv}}" direction="out"/>
    </method>
    <method name="GetModule">
      <arg name="id" type="s" direction="in"/>
      <arg name="module" type="a{{sv}}" direction="out"/>
    </method>
    <method name="SetModuleEnabled">
      <arg name="id" type="s" direction="in"/>
      <arg name="enabled" type="b" direction="in"/>
      <arg name="module" type="a{{sv}}" direction="out"/>
    </method>
    <!-- Chaque entrée : key, type, signature, label, description, default,
         et selon le type choices, minimum, maximum. -->
    <method name="GetSettingsSchema">
      <arg name="id" type="s" direction="in"/>
      <arg name="schema" type="aa{{sv}}" direction="out"/>
    </method>
    <method name="GetSettings">
      <arg name="id" type="s" direction="in"/>
      <arg name="settings" type="a{{sv}}" direction="out"/>
    </method>
    <method name="SetSetting">
      <arg name="id" type="s" direction="in"/>
      <arg name="key" type="s" direction="in"/>
      <arg name="value" type="v" direction="in"/>
    </method>
    <method name="ResetSetting">
      <arg name="id" type="s" direction="in"/>
      <arg name="key" type="s" direction="in"/>
    </method>
    <method name="CallAction">
      <arg name="id" type="s" direction="in"/>
      <arg name="action" type="s" direction="in"/>
      <arg name="params" type="a{{sv}}" direction="in"/>
      <arg name="result" type="a{{sv}}" direction="out"/>
    </method>
    <property name="Version" type="s" access="read"/>
    <signal name="ModuleStateChanged">
      <arg name="id" type="s"/>
      <arg name="module" type="a{{sv}}"/>
    </signal>
    <signal name="SettingChanged">
      <arg name="id" type="s"/>
      <arg name="key" type="s"/>
      <arg name="value" type="v"/>
    </signal>
    <signal name="ModuleEvent">
      <arg name="id" type="s"/>
      <arg name="event" type="s"/>
      <arg name="data" type="a{{sv}}"/>
    </signal>
  </interface>
</node>
"""

_INT64 = range(-(2**63), 2**63)


class BusNameTakenError(RuntimeError):
    """Une autre instance possède déjà le nom, ou le bus est injoignable."""


def to_variant(value: Any) -> GLib.Variant:
    """Convertit une valeur Python en ``GLib.Variant`` en devinant son type."""
    if isinstance(value, GLib.Variant):
        return value
    if isinstance(value, bool):
        return GLib.Variant("b", value)
    if isinstance(value, int):
        if value not in _INT64:
            raise TypeError(f"Entier hors limites pour D-Bus : {value}")
        return GLib.Variant("x", value)
    if isinstance(value, float):
        return GLib.Variant("d", value)
    if isinstance(value, str):
        return GLib.Variant("s", value)
    if isinstance(value, (bytes, bytearray)):
        return GLib.Variant("ay", bytes(value))
    if isinstance(value, Mapping):
        return GLib.Variant("a{sv}", vardict(value))
    if isinstance(value, (list, tuple)):
        if all(isinstance(item, str) for item in value):
            return GLib.Variant("as", list(value))
        if all(isinstance(item, Mapping) for item in value):
            return GLib.Variant("aa{sv}", [vardict(item) for item in value])
        return GLib.Variant("av", [to_variant(item) for item in value])
    raise TypeError(f"Type non transmissible par D-Bus : {type(value).__name__}")


def vardict(mapping: Mapping[str, Any]) -> dict[str, GLib.Variant]:
    """Prépare un dictionnaire pour une signature ``a{sv}`` (les ``None`` sont omis)."""
    return {str(key): to_variant(value) for key, value in mapping.items() if value is not None}


def setting_variant(setting: Setting, value: Any) -> GLib.Variant:
    return GLib.Variant(setting.dbus_signature, value)


class DBusService:
    def __init__(self, manager: ModuleManager, env: Environment, *, replace: bool = False) -> None:
        self.manager = manager
        self.env = env
        self.replace = replace
        #: Appelé si une autre instance lancée avec ``--replace`` prend le nom.
        self.on_name_lost: Callable[[], None] | None = None
        self._connection: Gio.DBusConnection | None = None
        self._owner_id = 0
        self._registration_id = 0
        self._tasks: set[asyncio.Future[Any]] = set()
        self._interface = Gio.DBusNodeInfo.new_for_xml(INTROSPECTION_XML).lookup_interface(
            INTERFACE
        )
        self._methods: dict[str, Callable[..., Any]] = {
            "GetEnvironment": self._get_environment,
            "ListModules": self._list_modules,
            "GetModule": self._get_module,
            "SetModuleEnabled": self._set_module_enabled,
            "GetSettingsSchema": self._get_settings_schema,
            "GetSettings": self._get_settings,
            "SetSetting": self._set_setting,
            "ResetSetting": self._reset_setting,
            "CallAction": self._call_action,
        }

    # -- cycle de vie --------------------------------------------------------------

    async def start(self, bus_type: Gio.BusType = Gio.BusType.SESSION) -> None:
        """Prend le nom sur le bus. Lève :class:`BusNameTakenError` en cas d'échec."""
        loop = asyncio.get_running_loop()
        acquired: asyncio.Future[None] = loop.create_future()

        def on_bus_acquired(connection: Gio.DBusConnection, _name: str) -> None:
            self._connection = connection
            self._registration_id = connection.register_object(
                OBJECT_PATH, self._interface, self._on_method_call, self._on_get_property, None
            )

        def on_name_acquired(_connection: Gio.DBusConnection, name: str) -> None:
            log.info("Nom D-Bus acquis : %s", name)
            if not acquired.done():
                acquired.set_result(None)

        def on_name_lost(connection: Gio.DBusConnection | None, name: str) -> None:
            if not acquired.done():
                reason = (
                    "bus de session injoignable"
                    if connection is None
                    else "une autre instance tourne déjà (relancer avec --replace)"
                )
                acquired.set_exception(BusNameTakenError(f"Impossible d'obtenir {name} : {reason}"))
                return
            if connection is None or connection.is_closed():
                log.warning("Connexion au bus de session perdue")
            else:
                log.warning("Nom D-Bus %s perdu (remplacé par une autre instance)", name)
            if self.on_name_lost is not None:
                self.on_name_lost()

        flags = Gio.BusNameOwnerFlags.DO_NOT_QUEUE | Gio.BusNameOwnerFlags.ALLOW_REPLACEMENT
        if self.replace:
            flags |= Gio.BusNameOwnerFlags.REPLACE
        self._owner_id = Gio.bus_own_name(
            bus_type, BUS_NAME, flags, on_bus_acquired, on_name_acquired, on_name_lost
        )
        try:
            await acquired
        except BaseException:
            self.stop()
            raise

        self.manager.state_listeners.append(self._emit_state_changed)
        self.manager.setting_listeners.append(self._emit_setting_changed)
        self.manager.event_listeners.append(self._emit_module_event)

    def stop(self) -> None:
        for listeners, callback in (
            (self.manager.state_listeners, self._emit_state_changed),
            (self.manager.setting_listeners, self._emit_setting_changed),
            (self.manager.event_listeners, self._emit_module_event),
        ):
            if callback in listeners:
                listeners.remove(callback)
        for task in list(self._tasks):
            task.cancel()
        if self._connection is not None and self._registration_id:
            self._connection.unregister_object(self._registration_id)
            self._registration_id = 0
        if self._owner_id:
            Gio.bus_unown_name(self._owner_id)
            self._owner_id = 0
        self._connection = None

    # -- méthodes --------------------------------------------------------------------

    def _get_environment(self) -> tuple[Any, ...]:
        return (vardict(self.env.to_dict()),)

    def _list_modules(self) -> tuple[Any, ...]:
        return ([vardict(state.to_dict()) for state in self.manager.states()],)

    def _get_module(self, module_id: str) -> tuple[Any, ...]:
        return (vardict(self.manager.state(module_id).to_dict()),)

    async def _set_module_enabled(self, module_id: str, enabled: bool) -> tuple[Any, ...]:
        state = await self.manager.set_enabled(module_id, enabled)
        return (vardict(state.to_dict()),)

    def _get_settings_schema(self, module_id: str) -> tuple[Any, ...]:
        schema = []
        for setting in self.manager.registry.info(module_id).settings:
            entry = vardict(setting.describe())
            entry["default"] = setting_variant(setting, setting.default_value())
            entry["signature"] = GLib.Variant("s", setting.dbus_signature)
            schema.append(entry)
        return (schema,)

    def _get_settings(self, module_id: str) -> tuple[Any, ...]:
        info = self.manager.registry.info(module_id)
        values = self.manager.settings(module_id)
        return ({s.key: setting_variant(s, values[s.key]) for s in info.settings},)

    def _set_setting(self, module_id: str, key: str, value: Any) -> None:
        self.manager.set_setting(module_id, key, value)

    def _reset_setting(self, module_id: str, key: str) -> None:
        self.manager.reset_setting(module_id, key)

    async def _call_action(
        self, module_id: str, action: str, params: dict[str, Any]
    ) -> tuple[Any, ...]:
        result = await self.manager.call_action(module_id, action, params)
        return (vardict(result),)

    # -- signaux ---------------------------------------------------------------------

    def _emit_state_changed(self, state: ModuleState) -> None:
        self._emit("ModuleStateChanged", "(sa{sv})", (state.info.id, vardict(state.to_dict())))

    def _emit_setting_changed(self, module_id: str, setting: Setting, value: Any) -> None:
        self._emit(
            "SettingChanged", "(ssv)", (module_id, setting.key, setting_variant(setting, value))
        )

    def _emit_module_event(self, module_id: str, event: str, data: dict[str, Any]) -> None:
        self._emit("ModuleEvent", "(ssa{sv})", (module_id, event, vardict(data)))

    def _emit(self, name: str, signature: str, args: tuple[Any, ...]) -> None:
        if self._connection is None:
            return
        self._connection.emit_signal(
            None, OBJECT_PATH, INTERFACE, name, GLib.Variant(signature, args)
        )

    # -- plomberie Gio -----------------------------------------------------------------

    def _on_get_property(
        self, _conn: Any, _sender: str, _path: str, _iface: str, name: str
    ) -> GLib.Variant | None:
        if name == "Version":
            return GLib.Variant("s", __version__)
        return None

    def _on_method_call(
        self,
        _conn: Gio.DBusConnection,
        _sender: str,
        _path: str,
        _iface: str,
        method: str,
        parameters: GLib.Variant,
        invocation: Gio.DBusMethodInvocation,
    ) -> None:
        handler = self._methods.get(method)
        if handler is None:
            invocation.return_dbus_error(
                "org.freedesktop.DBus.Error.UnknownMethod", f"Méthode inconnue : {method}"
            )
            return
        out_signature = self._out_signature(method)
        try:
            result = handler(*parameters.unpack())
        except Exception as exc:
            self._reply_error(invocation, method, exc)
            return
        if inspect.isawaitable(result):
            task = asyncio.ensure_future(self._finish(result, invocation, method, out_signature))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        else:
            self._reply(invocation, out_signature, result)

    async def _finish(
        self,
        pending: Any,
        invocation: Gio.DBusMethodInvocation,
        method: str,
        out_signature: str,
    ) -> None:
        try:
            result = await pending
        except asyncio.CancelledError:
            invocation.return_dbus_error("org.saturn.Error.Cancelled", "Le démon s'arrête")
            raise
        except Exception as exc:
            self._reply_error(invocation, method, exc)
            return
        self._reply(invocation, out_signature, result)

    def _out_signature(self, method: str) -> str:
        info = self._interface.lookup_method(method)
        return "(" + "".join(arg.signature for arg in info.out_args) + ")"

    @staticmethod
    def _reply(invocation: Gio.DBusMethodInvocation, signature: str, result: Any) -> None:
        if signature == "()":
            invocation.return_value(None)
        else:
            invocation.return_value(GLib.Variant(signature, result))

    @staticmethod
    def _reply_error(invocation: Gio.DBusMethodInvocation, method: str, exc: Exception) -> None:
        if isinstance(exc, SaturnError):
            invocation.return_dbus_error(exc.dbus_name, str(exc))
        elif isinstance(exc, TypeError):
            log.exception("Arguments invalides pour %s", method)
            invocation.return_dbus_error("org.freedesktop.DBus.Error.InvalidArgs", str(exc))
        else:
            log.exception("Erreur interne pendant %s", method)
            invocation.return_dbus_error("org.saturn.Error.Failed", "Erreur interne du démon")
