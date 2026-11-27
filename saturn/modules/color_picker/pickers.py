"""Prélever une couleur à l'écran, quel que soit le bureau.

Dans l'ordre : le portail XDG (``Screenshot.PickColor`` : GNOME, KDE…), puis
``hyprpicker`` (Hyprland), ``grim`` + ``slurp`` (Sway et autres wlroots) et
``xcolor`` (X11). Chacun laisse l'utilisateur cliquer sur un point de l'écran.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import os
import re
import shutil

from gi.repository import Gio, GLib

from saturn import dbus_async
from saturn.modules.color_picker.colors import RGB, from_unit, parse_hex

#: Laisse le temps de viser, mais pas indéfiniment.
PICK_TIMEOUT = 300.0

_tokens = itertools.count(1)


class PickCancelled(Exception):
    """L'utilisateur a annulé (Échap, clic droit…)."""


class PickUnavailable(Exception):
    """Aucune méthode de prélèvement ne marche sur ce bureau."""


async def pick_portal(log: logging.Logger) -> RGB:
    bus = await dbus_async.get_bus(Gio.BusType.SESSION)
    name = "org.freedesktop.portal.Desktop"
    token = f"saturn{os.getpid()}_{next(_tokens)}"
    sender = (bus.get_unique_name() or ":0").lstrip(":").replace(".", "_")
    expected = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
    response: asyncio.Future[tuple[int, dict]] = asyncio.get_running_loop().create_future()

    def on_response(_conn, _sender, _path, _iface, _signal, params) -> None:
        if not response.done():
            code, results = params.unpack()
            response.set_result((int(code), dict(results)))

    subscription = bus.signal_subscribe(
        name, "org.freedesktop.portal.Request", "Response", expected, None,
        Gio.DBusSignalFlags.NONE, on_response,
    )
    try:
        await dbus_async.call(
            bus, name, "/org/freedesktop/portal/desktop", "org.freedesktop.portal.Screenshot", "PickColor",
            GLib.Variant("(sa{sv})", ("", {"handle_token": GLib.Variant("s", token)})),
            "(o)", auto_start=True,
        )
        code, results = await asyncio.wait_for(response, PICK_TIMEOUT)
    finally:
        bus.signal_unsubscribe(subscription)
    if code == 1:
        raise PickCancelled()
    if code != 0 or "color" not in results:
        raise GLib.Error(f"Le portail n'a pas pu prélever de couleur (réponse {code})")
    return from_unit(*results["color"])


async def _run(*argv: str, timeout: float = PICK_TIMEOUT) -> tuple[int, bytes]:
    process = await asyncio.create_subprocess_exec(
        *argv, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        out, _err = await asyncio.wait_for(process.communicate(), timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise PickCancelled() from None
    return process.returncode or 0, out


_HEX_IN_TEXT = re.compile(r"#?[0-9a-fA-F]{6}\b")


async def pick_hex_command(*argv: str) -> RGB:
    """Outils qui écrivent la couleur en HEX sur leur sortie (hyprpicker, xcolor)."""
    code, out = await _run(*argv)
    match = _HEX_IN_TEXT.search(out.decode(errors="replace"))
    if code != 0 or not match:
        raise PickCancelled()
    return parse_hex(match.group(0))


async def pick_grim_slurp() -> RGB:
    code, out = await _run("slurp", "-p", "-b", "#00000000")
    geometry = out.decode().strip()
    if code != 0 or not geometry:
        raise PickCancelled()
    code, ppm = await _run("grim", "-g", geometry, "-t", "ppm", "-", timeout=10)
    if code != 0:
        raise PickUnavailable("grim n'a pas pu capturer l'écran")
    return read_ppm_pixel(ppm)


def read_ppm_pixel(data: bytes) -> RGB:
    """Premier pixel d'une image PPM binaire (P6, 8 bits)."""
    fields: list[bytes] = []
    position = 0
    while len(fields) < 4:
        while data[position:position + 1].isspace():
            position += 1
        if data[position:position + 1] == b"#":
            position = data.index(b"\n", position) + 1
            continue
        end = position
        while not data[end:end + 1].isspace():
            end += 1
        fields.append(data[position:end])
        position = end
    if fields[0] != b"P6" or int(fields[3]) > 255:
        raise ValueError("PPM inattendu")
    pixel = data[position + 1:position + 4]
    return pixel[0], pixel[1], pixel[2]


async def pick_color(log: logging.Logger) -> RGB:
    """Laisse l'utilisateur viser un point ; lève PickCancelled ou PickUnavailable."""
    try:
        return await pick_portal(log)
    except PickCancelled:
        raise
    except (GLib.Error, TimeoutError) as exc:
        log.debug("Portail de capture : %s", getattr(exc, "message", exc))

    if shutil.which("hyprpicker"):
        return await pick_hex_command("hyprpicker", "--format=hex", "--no-fancy")
    if shutil.which("grim") and shutil.which("slurp"):
        return await pick_grim_slurp()
    if shutil.which("xcolor"):
        return await pick_hex_command("xcolor")
    raise PickUnavailable(
        "Aucune pipette ici : il faut le portail XDG (GNOME, KDE), hyprpicker, grim + slurp ou xcolor."
    )
