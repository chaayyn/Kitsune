"""Appels D-Bus asynchrones (Gio) utilisables avec ``await`` depuis les modules.

Le démon fait tourner asyncio sur la boucle GLib : les rappels de Gio arrivent
dans le même fil que les coroutines, il suffit de résoudre un ``Future``.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from gi.repository import Gio, GLib

#: Délai par défaut d'un appel, en millisecondes.
TIMEOUT_MS = 5000


async def get_bus(bus_type: Gio.BusType) -> Gio.DBusConnection:
    """Connexion partagée au bus de session ou au bus système."""
    future: asyncio.Future[Gio.DBusConnection] = asyncio.get_running_loop().create_future()

    def done(_source: Any, result: Gio.AsyncResult) -> None:
        if future.cancelled():
            return
        try:
            future.set_result(Gio.bus_get_finish(result))
        except GLib.Error as exc:
            future.set_exception(exc)

    Gio.bus_get(bus_type, None, done)
    return await future


async def call(
    connection: Gio.DBusConnection,
    name: str,
    path: str,
    interface: str,
    method: str,
    params: GLib.Variant | None = None,
    reply_type: str | None = None,
    *,
    auto_start: bool = False,
    timeout_ms: int = TIMEOUT_MS,
) -> GLib.Variant:
    reply, _fds = await call_with_fds(
        connection, name, path, interface, method, params, reply_type,
        auto_start=auto_start, timeout_ms=timeout_ms,
    )
    return reply


async def call_with_fds(
    connection: Gio.DBusConnection,
    name: str,
    path: str,
    interface: str,
    method: str,
    params: GLib.Variant | None = None,
    reply_type: str | None = None,
    *,
    auto_start: bool = False,
    timeout_ms: int = TIMEOUT_MS,
) -> tuple[GLib.Variant, list[int]]:
    """Comme :func:`call`, mais renvoie aussi les descripteurs reçus (à fermer par l'appelant)."""
    future: asyncio.Future[tuple[GLib.Variant, list[int]]] = (
        asyncio.get_running_loop().create_future()
    )

    def done(conn: Gio.DBusConnection, result: Gio.AsyncResult) -> None:
        try:
            reply, fd_list = conn.call_with_unix_fd_list_finish(result)
        except GLib.Error as exc:
            if not future.cancelled():
                future.set_exception(exc)
            return
        fds = fd_list.steal_fds() if fd_list is not None else []
        if future.cancelled():
            for fd in fds:
                _close(fd)
            return
        future.set_result((reply, list(fds)))

    flags = Gio.DBusCallFlags.NONE if auto_start else Gio.DBusCallFlags.NO_AUTO_START
    connection.call_with_unix_fd_list(
        name, path, interface, method, params,
        GLib.VariantType.new(reply_type) if reply_type else None,
        flags, timeout_ms, None, None, done,
    )
    return await future


def _close(fd: int) -> None:
    try:
        os.close(fd)
    except OSError:
        pass
