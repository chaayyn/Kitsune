from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from gi.repository import Gio, GLib

from saturn.config import Config
from saturn.errors import ActionError
from saturn.manager import ModuleManager
from saturn.modules.color_picker import module as picker_module
from saturn.modules.color_picker import pickers
from saturn.modules.color_picker.colors import format_color, from_unit, parse_hex, to_hex
from saturn.modules.color_picker.store import ColorStore
from saturn.registry import Registry
from saturn.storage import Database
from tests.conftest import needs_dbus, spawn_daemon, stop_process, wait_for_owner

# -- conversions et stockage ------------------------------------------------------------


@pytest.mark.parametrize(
    ("rgb", "fmt", "text"),
    [
        ((232, 180, 74), "hex", "#E8B44A"),
        ((232, 180, 74), "rgb", "rgb(232, 180, 74)"),
        ((232, 180, 74), "hsl", "hsl(40, 77%, 60%)"),
        ((0, 0, 0), "hsl", "hsl(0, 0%, 0%)"),
        ((255, 255, 255), "none", "#FFFFFF"),
    ],
)
def test_formats(rgb, fmt, text) -> None:
    assert format_color(rgb, fmt) == text


def test_parsing() -> None:
    assert parse_hex("#e8b44a") == parse_hex("E8B44A") == (232, 180, 74)
    assert to_hex(from_unit(1.0, 0.5, 0.0)) == "#FF8000"
    for bad in ("", "#12345", "#GGGGGG", "rgb(1,2,3)"):
        with pytest.raises(ValueError):
            parse_hex(bad)


def test_ppm_pixel() -> None:
    assert pickers.read_ppm_pixel(b"P6\n# grim\n1 1\n255\n\xe8\xb4\x4a") == (232, 180, 74)
    with pytest.raises(ValueError):
        pickers.read_ppm_pixel(b"P5\n1 1\n255\n\x00")


def test_store_dedup_and_trim(tmp_path: Path) -> None:
    store = ColorStore(Database(tmp_path / "c.db").connection)
    for i, hex_value in enumerate(["#000001", "#000002", "#000003", "#000001"]):
        store.add(hex_value, keep=3, now=i)
    assert [c["hex"] for c in store.list()] == ["#000001", "#000003", "#000002"]
    store.add("#000004", keep=2, now=10)
    assert [c["hex"] for c in store.list()] == ["#000004", "#000001"]
    assert store.delete("#000004") and not store.delete("#000004")


# -- outils en ligne de commande (faux binaires) ---------------------------------------------


def _fake_bin(directory: Path, name: str, script: str) -> None:
    path = directory / name
    path.write_text("#!/bin/sh\n" + script)
    path.chmod(0o755)


def test_command_pickers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ppm = tmp_path / "pixel.ppm"
    ppm.write_bytes(b"P6\n1 1\n255\n\x10\x20\x30")
    _fake_bin(tmp_path, "slurp", 'echo "640,400 1x1"\n')
    _fake_bin(tmp_path, "grim", f'[ "$2" = "640,400 1x1" ] && cat {ppm}\n')
    _fake_bin(tmp_path, "hyprpicker", 'echo "#a1B2c3"\n')
    _fake_bin(tmp_path, "xcolor", "exit 1\n")  # Échap : rien sur la sortie
    monkeypatch.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")

    async def scenario() -> None:
        assert await pickers.pick_grim_slurp() == (16, 32, 48)
        assert await pickers.pick_hex_command("hyprpicker", "--format=hex") == (161, 178, 195)
        with pytest.raises(pickers.PickCancelled):
            await pickers.pick_hex_command("xcolor")

    asyncio.run(scenario())


# -- module (prélèvement simulé) ----------------------------------------------------------


@pytest.fixture
def colors(env, monkeypatch: pytest.MonkeyPatch) -> tuple[ModuleManager, list[Any], list[str]]:
    results: list[Any] = []
    copied: list[str] = []

    async def fake_pick(_log):
        await asyncio.sleep(0.01)
        outcome = results.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def fake_copy(_ctx, text):
        copied.append(text)
        return True

    monkeypatch.setattr(picker_module.ColorPickerModule, "picker", staticmethod(fake_pick))
    monkeypatch.setattr(picker_module.ColorPickerModule, "copier", staticmethod(fake_copy))
    manager = ModuleManager(Registry(), Config.load(), env)
    manager.discover()
    return manager, results, copied


def test_pick_flow(colors, run) -> None:
    manager, results, copied = colors
    events: list[tuple[str, dict]] = []
    manager.event_listeners.append(lambda mid, ev, data: mid == "color_picker" and events.append((ev, data)))

    async def scenario() -> None:
        await manager.start()
        call = manager.call_action
        results.extend([(232, 180, 74), pickers.PickCancelled(), (1, 2, 3)])

        assert await call("color_picker", "pick", {}) == {"started": True}
        assert await call("color_picker", "pick", {}) == {"started": False}  # un seul à la fois
        await asyncio.sleep(0.05)
        assert copied == ["#E8B44A"]

        await call("color_picker", "pick", {})
        await asyncio.sleep(0.05)

        manager.set_setting("color_picker", "copy_format", "rgb")
        await call("color_picker", "pick", {})
        await asyncio.sleep(0.05)
        assert copied[-1] == "rgb(1, 2, 3)"

        listed = (await call("color_picker", "list", {}))["colors"]
        assert [c["hex"] for c in listed] == ["#010203", "#E8B44A"]
        assert listed[1]["hsl"] == "hsl(40, 77%, 60%)"

        assert (await call("color_picker", "copy", {"hex": "e8b44a", "format": "hsl"}))["text"] == "hsl(40, 77%, 60%)"
        with pytest.raises(ActionError):
            await call("color_picker", "copy", {"hex": "pas une couleur"})

        manager.set_setting("color_picker", "history_size", 1)
        assert len((await call("color_picker", "list", {}))["colors"]) == 1

        # Rien d'installé pour viser : avertissement sous le module.
        results.append(pickers.PickUnavailable("Aucune pipette ici"))
        await call("color_picker", "pick", {})
        await asyncio.sleep(0.05)
        assert manager.state("color_picker").notice == "Aucune pipette ici"
        await manager.stop()

    run(scenario())
    picked = [data for ev, data in events if ev == "picked"]
    assert [p["status"] for p in picked] == ["ok", "cancelled", "ok", "error"]
    assert picked[0] | {} == {"status": "ok", "hex": "#E8B44A", "rgb": "rgb(232, 180, 74)",
                              "hsl": "hsl(40, 77%, 60%)", "text": "#E8B44A", "copied": True}


# -- bout en bout : vrai démon, faux portail, copie relayée par « l'extension » -------------

FAKE = Path(__file__).with_name("fake_desktop_services.py")


@needs_dbus
@pytest.mark.parametrize("answer", ["#3366CC", "cancel"])
def test_portal_pick_and_shell_copy(bus, monkeypatch: pytest.MonkeyPatch, answer: str) -> None:
    address, connection = bus
    monkeypatch.setenv("DBUS_SYSTEM_BUS_ADDRESS", address)
    fakes = subprocess.Popen([sys.executable, str(FAKE), "--pick", answer],
                             env=dict(os.environ, DBUS_SESSION_BUS_ADDRESS=address))
    # Ce processus joue l'extension GNOME : il reçoit les demandes d'écriture.
    connection.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "RequestName",
                         GLib.Variant("(su)", ("org.saturn.Shell", 4)), None, 0, -1, None)
    events: list[tuple[str, dict]] = []
    connection.signal_subscribe("org.saturn.Daemon", "org.saturn.Daemon1", "ModuleEvent", None, None,
                                Gio.DBusSignalFlags.NONE,
                                lambda *a: events.append(tuple(a[5].unpack()[1:])))
    time.sleep(0.4)
    daemon = spawn_daemon(address)
    try:
        wait_for_owner(connection)
        reply = connection.call_sync("org.saturn.Daemon", "/org/saturn/Daemon", "org.saturn.Daemon1", "CallAction",
                                     GLib.Variant("(ssa{sv})", ("color_picker", "pick", {})), None, 0, 5000, None)
        assert reply.unpack()[0] == {"started": True}
        context = GLib.MainContext.default()
        deadline = time.monotonic() + 5
        while not any(ev == "picked" for ev, _ in events) and time.monotonic() < deadline:
            context.iteration(False)
            time.sleep(0.01)
        picked = next(data for ev, data in events if ev == "picked")
        if answer == "cancel":
            assert picked == {"status": "cancelled"}
        else:
            assert picked["hex"] == "#3366CC" and picked["copied"] is True
            while not any(ev == "write" for ev, _ in events) and time.monotonic() < deadline:
                context.iteration(False)
            assert ("write", {"text": "#3366CC"}) in events
    finally:
        assert stop_process(daemon) == 0, daemon.stderr.read()
        stop_process(fakes)
