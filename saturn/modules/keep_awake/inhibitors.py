"""Empêcher la mise en veille, quel que soit le bureau.

Trois choses peuvent être bloquées :

* ``idle`` : l'écran ne s'éteint pas et ne se verrouille pas ;
* ``suspend`` : l'ordinateur ne se met pas en veille tout seul ;
* ``lid`` : rabattre le capot d'un portable ne le met pas en veille.

Côté session, on essaie dans l'ordre le gestionnaire de session GNOME, le
portail XDG (KDE, wlroots…) puis ``org.freedesktop.ScreenSaver`` (écran
seulement). Ce qui reste est demandé à systemd-logind, seul à gérer le capot.

Toutes les inhibitions sont liées à la connexion D-Bus du démon : si saturnd
s'arrête, même brutalement, le bureau les oublie de lui-même.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from gi.repository import Gio, GLib

from saturn import dbus_async

APP_ID = "saturn"

IDLE = "idle"
SUSPEND = "suspend"
LID = "lid"

# org.gnome.SessionManager.Inhibit et org.freedesktop.portal.Inhibit partagent ces drapeaux.
_FLAG_SUSPEND = 4
_FLAG_IDLE = 8
_LOGIND_WHAT = {IDLE: "idle", SUSPEND: "sleep", LID: "handle-lid-switch"}

#: Temps laissé au portail pour signaler un refus de son service (KDE, GNOME…).
PORTAL_SETTLE_SECONDS = 0.5
_tokens = itertools.count(1)


@dataclass
class Lease:
    """Une inhibition obtenue auprès d'un service, à rendre avec :meth:`release`."""

    backend: str
    covers: frozenset[str]
    _release: Callable[[], Awaitable[None]] = field(repr=False)

    async def release(self) -> None:
        await self._release()


class Inhibitor(Protocol):
    async def acquire(self, wanted: set[str], reason: str) -> tuple[list[Lease], set[str]]:
        """Renvoie les inhibitions obtenues et ce qui n'a pas pu être couvert."""
        ...


def _flags(kinds: set[str]) -> int:
    return (_FLAG_IDLE if IDLE in kinds else 0) | (_FLAG_SUSPEND if SUSPEND in kinds else 0)


class DBusInhibitor:
    def __init__(self, log: logging.Logger | None = None) -> None:
        self.log = log or logging.getLogger(__name__)

    async def acquire(self, wanted: set[str], reason: str) -> tuple[list[Lease], set[str]]:
        leases: list[Lease] = []
        remaining = set(wanted)

        session_kinds = remaining & {IDLE, SUSPEND}
        if session_kinds:
            try:
                session = await dbus_async.get_bus(Gio.BusType.SESSION)
            except GLib.Error as exc:
                self.log.warning("Bus de session indisponible : %s", exc.message)
            else:
                for attempt in (self._gnome_session, self._portal, self._screensaver):
                    try:
                        lease = await attempt(session, session_kinds, reason)
                    except GLib.Error as exc:
                        self.log.debug("%s : %s", attempt.__name__, exc.message)
                        continue
                    leases.append(lease)
                    remaining -= lease.covers
                    break

        if remaining:
            try:
                lease = await self._logind(remaining, reason)
            except GLib.Error as exc:
                self.log.warning("systemd-logind a refusé l'inhibition : %s", exc.message)
            else:
                leases.append(lease)
                remaining -= lease.covers

        return leases, remaining

    # -- services de session ----------------------------------------------------------

    async def _gnome_session(self, bus: Gio.DBusConnection, kinds: set[str], reason: str) -> Lease:
        name, path, iface = "org.gnome.SessionManager", "/org/gnome/SessionManager", "org.gnome.SessionManager"
        reply = await dbus_async.call(
            bus, name, path, iface, "Inhibit",
            GLib.Variant("(susu)", (APP_ID, 0, reason, _flags(kinds))), "(u)",
        )
        (cookie,) = reply.unpack()

        async def release() -> None:
            await dbus_async.call(bus, name, path, iface, "Uninhibit", GLib.Variant("(u)", (cookie,)))

        return Lease("gnome-session", frozenset(kinds), release)

    async def _portal(self, bus: Gio.DBusConnection, kinds: set[str], reason: str) -> Lease:
        """Portail XDG. Il répond avant d'avoir interrogé son service : si celui-ci
        échoue, l'objet de requête disparaît. On vérifie donc qu'il tient."""
        name = "org.freedesktop.portal.Desktop"
        token = f"saturn{os.getpid()}_{next(_tokens)}"
        sender = (bus.get_unique_name() or ":0").lstrip(":").replace(".", "_")
        expected = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
        response: asyncio.Future[int] = asyncio.get_running_loop().create_future()

        def on_response(_conn, _sender, _path, _iface, _signal, params) -> None:
            if not response.done():
                response.set_result(int(params.unpack()[0]))

        subscription = bus.signal_subscribe(
            name, "org.freedesktop.portal.Request", "Response", expected, None,
            Gio.DBusSignalFlags.NONE, on_response,
        )
        try:
            reply = await dbus_async.call(
                bus, name, "/org/freedesktop/portal/desktop", "org.freedesktop.portal.Inhibit", "Inhibit",
                GLib.Variant("(sua{sv})", ("", _flags(kinds), {
                    "reason": GLib.Variant("s", reason),
                    "handle_token": GLib.Variant("s", token),
                })),
                "(o)", auto_start=True,
            )
            (handle,) = reply.unpack()
            try:
                code = await asyncio.wait_for(asyncio.shield(response), PORTAL_SETTLE_SECONDS)
            except TimeoutError:
                code = 0
            if code != 0:
                raise GLib.Error(f"Le portail a refusé l'inhibition (réponse {code})")
            # Lève une erreur si la requête n'est plus exportée (service en échec).
            await dbus_async.call(
                bus, name, handle, "org.freedesktop.DBus.Properties", "GetAll",
                GLib.Variant("(s)", ("org.freedesktop.portal.Request",)), "(a{sv})",
            )
        finally:
            bus.signal_unsubscribe(subscription)

        async def release() -> None:
            await dbus_async.call(bus, name, handle, "org.freedesktop.portal.Request", "Close")

        return Lease("portal", frozenset(kinds), release)

    async def _screensaver(self, bus: Gio.DBusConnection, kinds: set[str], reason: str) -> Lease:
        if IDLE not in kinds:
            raise GLib.Error("org.freedesktop.ScreenSaver ne gère que l'écran")
        name = "org.freedesktop.ScreenSaver"
        path = "/org/freedesktop/ScreenSaver"
        reply = await dbus_async.call(
            bus, name, path, name, "Inhibit", GLib.Variant("(ss)", (APP_ID, reason)), "(u)",
        )
        (cookie,) = reply.unpack()

        async def release() -> None:
            await dbus_async.call(bus, name, path, name, "UnInhibit", GLib.Variant("(u)", (cookie,)))

        return Lease("screensaver", frozenset({IDLE}), release)

    # -- systemd-logind -----------------------------------------------------------------

    async def _logind(self, kinds: set[str], reason: str) -> Lease:
        system = await dbus_async.get_bus(Gio.BusType.SYSTEM)
        what = ":".join(_LOGIND_WHAT[kind] for kind in sorted(kinds))
        reply, fds = await dbus_async.call_with_fds(
            system, "org.freedesktop.login1", "/org/freedesktop/login1",
            "org.freedesktop.login1.Manager", "Inhibit",
            GLib.Variant("(ssss)", (what, "Saturn", reason, "block")), "(h)",
        )
        (index,) = reply.unpack()
        fd = fds[index]
        for other in fds:
            if other != fd:
                os.close(other)

        async def release() -> None:
            # logind lève l'inhibition dès que le descripteur est fermé.
            try:
                os.close(fd)
            except OSError:
                pass

        return Lease("logind", frozenset(kinds), release)


# -- batterie ------------------------------------------------------------------------------


class BatteryWatcher(Protocol):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    @property
    def on_battery(self) -> bool: ...

    @property
    def percentage(self) -> float: ...


class UPowerWatcher:
    """Suit la charge (``DisplayDevice``) et le passage sur batterie via UPower."""

    NAME = "org.freedesktop.UPower"
    ROOT = "/org/freedesktop/UPower"
    DEVICE = "/org/freedesktop/UPower/devices/DisplayDevice"

    def __init__(self, on_change: Callable[[], None], log: logging.Logger | None = None) -> None:
        self._on_change = on_change
        self.log = log or logging.getLogger(__name__)
        self._bus: Gio.DBusConnection | None = None
        self._subscription = 0
        self.on_battery = False
        self.percentage = 100.0

    async def start(self) -> None:
        if self._bus is not None:
            return
        try:
            self._bus = await dbus_async.get_bus(Gio.BusType.SYSTEM)
            on_battery = await self._get(self.ROOT, "org.freedesktop.UPower", "OnBattery")
            percentage = await self._get(self.DEVICE, "org.freedesktop.UPower.Device", "Percentage")
        except GLib.Error as exc:
            self.log.info("UPower indisponible, pas de surveillance de la batterie : %s", exc.message)
            self._bus = None
            return
        self.on_battery, self.percentage = bool(on_battery), float(percentage)
        self._subscription = self._bus.signal_subscribe(
            self.NAME, "org.freedesktop.DBus.Properties", "PropertiesChanged", None, None,
            Gio.DBusSignalFlags.NONE, self._on_properties_changed,
        )

    async def stop(self) -> None:
        if self._bus is not None and self._subscription:
            self._bus.signal_unsubscribe(self._subscription)
        self._subscription = 0
        self._bus = None

    async def _get(self, path: str, interface: str, prop: str) -> object:
        assert self._bus is not None
        reply = await dbus_async.call(
            self._bus, self.NAME, path, "org.freedesktop.DBus.Properties", "Get",
            GLib.Variant("(ss)", (interface, prop)), "(v)",
        )
        return reply.unpack()[0]

    def _on_properties_changed(self, _conn, _sender, path, _iface, _signal, params) -> None:
        _interface, changed, _invalidated = params.unpack()
        updated = False
        if path == self.ROOT and "OnBattery" in changed:
            self.on_battery = bool(changed["OnBattery"])
            updated = True
        if path == self.DEVICE and "Percentage" in changed:
            self.percentage = float(changed["Percentage"])
            updated = True
        if updated:
            self._on_change()
