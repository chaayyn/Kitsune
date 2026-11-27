from __future__ import annotations

import asyncio
import time
from typing import Any

from gi.repository import Gio, GLib

from saturn import dbus_async
from saturn.errors import ActionError
from saturn.module import Module, action
from saturn.modules.keep_awake.inhibitors import IDLE, DBusInhibitor, Lease

#: Extension GNOME de Saturn : elle affiche le voile depuis le Shell, qui bloque tout.
SHELL_BUS_NAME = "org.saturn.Shell"
#: Interface Qt : elle affiche le voile en plein écran ailleurs.
UI_BUS_NAME = "org.saturn.Ui"

REASON = "Mode nettoyage de Saturn"


class CleaningModule(Module):
    """Le démon tient l'horloge ; l'extension GNOME ou l'interface Qt affiche le voile.

    L'affichage suit l'évènement ``state-changed`` : ``surface`` dit qui doit
    l'afficher (``shell`` ou ``ui``). Le voile appelle ``stop`` quand on en sort.
    """

    # Remplaçable dans les tests.
    inhibitor_factory: Any = DBusInhibitor

    async def start(self) -> None:
        self._until = 0.0
        self._seconds = 0
        self._surface = ""
        self._block_pointer = False
        self._timer: asyncio.TimerHandle | None = None
        self._leases: list[Lease] = []
        self._tasks: set[asyncio.Task[Any]] = set()

    async def stop(self) -> None:
        await self._finish("stopped", emit=False)
        for task in list(self._tasks):
            task.cancel()

    @property
    def active(self) -> bool:
        return bool(self._until)

    # -- actions ------------------------------------------------------------------------

    @action()
    def status(self, _params: dict[str, Any]) -> dict[str, Any]:
        return self._status()

    @action("start")
    async def start_action(self, params: dict[str, Any]) -> dict[str, Any]:
        seconds = params.get("seconds")
        if seconds is None:
            seconds = int(self.ctx.setting("duration"))
        if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= 600:
            raise ActionError("Paramètre « seconds » : entre 1 et 600")
        if not self.active:
            self._surface = await self._pick_surface()
            self._block_pointer = bool(self.ctx.setting("block_pointer"))
            await self._hold_screen()
        self._seconds = seconds
        self._until = time.time() + seconds
        if self._timer is not None:
            self._timer.cancel()
        self._timer = asyncio.get_running_loop().call_later(seconds, self._on_timeout)
        self._emit("user")
        return self._status()

    @action("stop")
    async def stop_action(self, params: dict[str, Any]) -> dict[str, Any]:
        await self._finish(str(params.get("reason") or "user"))
        return self._status()

    # -- interne ------------------------------------------------------------------------

    async def _pick_surface(self) -> str:
        """``shell`` si l'extension GNOME tourne, sinon ``ui`` (lancée au besoin)."""
        try:
            bus = await dbus_async.get_bus(Gio.BusType.SESSION)
            if await _has_owner(bus, SHELL_BUS_NAME):
                return "shell"
            if not await _has_owner(bus, UI_BUS_NAME):
                try:
                    await dbus_async.call(
                        bus, "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                        "StartServiceByName", GLib.Variant("(su)", (UI_BUS_NAME, 0)), "(u)",
                        timeout_ms=15000,
                    )
                except GLib.Error as exc:
                    self.ctx.log.debug("Activation de l'interface : %s", exc.message)
                if not await _has_owner(bus, UI_BUS_NAME):
                    raise ActionError("Interface introuvable : lancez « saturn » (ou installez l'extension GNOME)")
        except GLib.Error as exc:
            raise ActionError(f"Bus de session indisponible : {exc.message}") from exc
        return "ui"

    async def _hold_screen(self) -> None:
        """Pendant le nettoyage, l'écran ne doit ni s'éteindre ni se verrouiller."""
        try:
            self._leases, _missing = await self.inhibitor_factory(self.ctx.log).acquire({IDLE}, REASON)
        except Exception as exc:  # confort seulement : le mode marche sans
            self.ctx.log.debug("Inhibition de l'écran impossible : %s", exc)
            self._leases = []

    async def _finish(self, reason: str, *, emit: bool = True) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        was_active = self.active
        self._until = 0.0
        self._seconds = 0
        leases, self._leases = self._leases, []
        for lease in leases:
            try:
                await lease.release()
            except Exception as exc:
                self.ctx.log.debug("Libération : %s", exc)
        if emit and was_active:
            self._emit(reason)

    def _on_timeout(self) -> None:
        self._timer = None
        task = asyncio.get_running_loop().create_task(self._finish("timer"))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _status(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "until": self._until,
            "seconds": self._seconds,
            "surface": self._surface if self.active else "",
            "block_pointer": self._block_pointer if self.active else False,
        }

    def _emit(self, reason: str) -> None:
        self.ctx.emit("state-changed", {**self._status(), "reason": reason})


async def _has_owner(bus: Gio.DBusConnection, name: str) -> bool:
    reply = await dbus_async.call(
        bus, "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
        "NameHasOwner", GLib.Variant("(s)", (name,)), "(b)",
    )
    return bool(reply.unpack()[0])
