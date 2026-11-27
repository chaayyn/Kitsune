from __future__ import annotations

import asyncio
import json
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
from saturn.modules.cleaning import module as cleaning
from saturn.modules.keep_awake.inhibitors import IDLE, Lease
from saturn.registry import Registry
from tests.conftest import call_daemon, needs_dbus, spawn_daemon, stop_process, wait_for_owner


class FakeInhibitor:
    held: list[frozenset[str]] = []

    def __init__(self, _log: Any = None) -> None:
        pass

    async def acquire(self, wanted: set[str], _reason: str) -> tuple[list[Lease], set[str]]:
        covers = frozenset(wanted)

        async def release() -> None:
            FakeInhibitor.held.remove(covers)

        FakeInhibitor.held.append(covers)
        return [Lease("fake", covers, release)], set()


@pytest.fixture
def pad(env, monkeypatch: pytest.MonkeyPatch) -> ModuleManager:
    FakeInhibitor.held = []

    async def surface(_self) -> str:
        return "shell"

    monkeypatch.setattr(cleaning.CleaningModule, "_pick_surface", surface)
    monkeypatch.setattr(cleaning.CleaningModule, "inhibitor_factory", FakeInhibitor)
    manager = ModuleManager(Registry(), Config.load(), env)
    manager.discover()
    return manager


def test_start_stop_and_timeout(pad: ModuleManager, run) -> None:
    events: list[dict[str, Any]] = []
    pad.event_listeners.append(lambda mid, ev, data: mid == "cleaning" and events.append(data))

    async def scenario() -> None:
        await pad.start()
        assert pad.is_running("cleaning")
        call = pad.call_action
        assert (await call("cleaning", "status", {}))["active"] is False

        pad.set_setting("cleaning", "block_pointer", True)
        state = await call("cleaning", "start", {})
        assert state["active"] and state["seconds"] == 60 and state["surface"] == "shell"
        assert state["block_pointer"] and 59 < state["until"] - time.time() <= 60
        assert FakeInhibitor.held == [frozenset({IDLE})]  # l'écran reste allumé pendant le nettoyage

        state = await call("cleaning", "stop", {})
        assert not state["active"] and state["surface"] == "" and FakeInhibitor.held == []

        await call("cleaning", "start", {"seconds": 1})
        await asyncio.sleep(1.2)
        assert (await call("cleaning", "status", {}))["active"] is False
        assert FakeInhibitor.held == []

        for bad in (0, 601, True, "10"):
            with pytest.raises(ActionError):
                await call("cleaning", "start", {"seconds": bad})
        await call("cleaning", "start", {"seconds": 30})
        await pad.stop()  # arrêt du démon : tout est rendu, sans évènement
        assert FakeInhibitor.held == []

    run(scenario())
    assert [(e["active"], e["reason"]) for e in events] == [
        (True, "user"), (False, "user"), (True, "user"), (False, "timer"), (True, "user"),
    ]


# -- bout en bout ---------------------------------------------------------------------------

FAKE = Path(__file__).with_name("fake_desktop_services.py")


def _own(connection: Gio.DBusConnection, name: str, release: bool = False) -> None:
    connection.call_sync(
        "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
        "ReleaseName" if release else "RequestName",
        GLib.Variant("(s)", (name,)) if release else GLib.Variant("(su)", (name, 4)),
        None, Gio.DBusCallFlags.NONE, -1, None,
    )


def _action(connection, name: str, params: dict[str, GLib.Variant] | None = None) -> dict[str, Any]:
    (result,) = call_daemon(connection, "CallAction", ("cleaning", name, params or {}), "(ssa{sv})")
    return result


@needs_dbus
def test_surface_and_screen_inhibition(bus, monkeypatch: pytest.MonkeyPatch) -> None:
    address, connection = bus
    monkeypatch.setenv("DBUS_SYSTEM_BUS_ADDRESS", address)
    fakes = subprocess.Popen([sys.executable, str(FAKE)], env=dict(os.environ, DBUS_SESSION_BUS_ADDRESS=address))
    time.sleep(0.4)
    daemon = spawn_daemon(address)
    try:
        wait_for_owner(connection)

        # Ni extension ni interface : rien ne pourrait afficher le voile.
        with pytest.raises(GLib.Error, match="Interface introuvable"):
            _action(connection, "start")

        _own(connection, "org.saturn.Shell")
        state = _action(connection, "start", {"seconds": GLib.Variant("x", 30)})
        assert state["surface"] == "shell" and state["seconds"] == 30
        reply = connection.call_sync("org.saturn.Test", "/org/saturn/Test", "org.saturn.Test1", "State",
                                     None, None, Gio.DBusCallFlags.NONE, 5000, None)
        assert list(json.loads(reply.unpack()[0])["gnome"].values()) == [8]  # écran seulement
        _action(connection, "stop")
        _own(connection, "org.saturn.Shell", release=True)

        _own(connection, "org.saturn.Ui")
        assert _action(connection, "start")["surface"] == "ui"
        assert _action(connection, "stop", {"reason": GLib.Variant("s", "user")})["active"] is False
        reply = connection.call_sync("org.saturn.Test", "/org/saturn/Test", "org.saturn.Test1", "State",
                                     None, None, Gio.DBusCallFlags.NONE, 5000, None)
        assert not any(json.loads(reply.unpack()[0]).values())
    finally:
        assert stop_process(daemon) == 0, daemon.stderr.read()
        stop_process(fakes)
