"""Copier un texte depuis le démon, selon le bureau."""

from __future__ import annotations

import shutil

from gi.repository import Gio, GLib

from saturn import dbus_async
from saturn.desktop import Family
from saturn.module import ModuleContext
from saturn.modules.clipboard.backends import _feed

SHELL_BUS_NAME = "org.saturn.Shell"


async def copy_text(ctx: ModuleContext, text: str) -> bool:
    """Renvoie ``False`` si rien ne permet d'écrire le presse-papiers ici."""
    env = ctx.env
    if env.is_wayland and env.family is Family.GNOME:
        # Sous GNOME Wayland, seule l'extension peut écrire : elle relaie l'évènement « write ».
        try:
            bus = await dbus_async.get_bus(Gio.BusType.SESSION)
            reply = await dbus_async.call(
                bus, "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                "NameHasOwner", GLib.Variant("(s)", (SHELL_BUS_NAME,)), "(b)",
            )
        except GLib.Error:
            return False
        if not reply.unpack()[0]:
            return False
        ctx.emit("write", {"text": text})
        return True
    try:
        if env.is_wayland and shutil.which("wl-copy"):
            await _feed("wl-copy", "--type", "text/plain;charset=utf-8", data=text.encode())
            return True
        if env.is_x11 and shutil.which("xclip"):
            await _feed("xclip", "-selection", "clipboard", "-in", data=text.encode())
            return True
        if env.is_x11 and shutil.which("xsel"):
            await _feed("xsel", "--clipboard", "--input", data=text.encode())
            return True
    except (OSError, TimeoutError) as exc:
        ctx.log.warning("Copie impossible : %s", exc)
    return False
