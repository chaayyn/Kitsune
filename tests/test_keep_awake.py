from __future__ import annotations

import asyncio
import json
import os
import signal
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
from saturn.modules.keep_awake import module as keep_awake
from saturn.modules.keep_awake.inhibitors import IDLE, LID, SUSPEND, Lease
from saturn.registry import Registry
from tests.conftest import call_daemon, needs_dbus, spawn_daemon, stop_process, wait_for_owner


class FakeInhibitor:
    """Couvre tout sauf ``refuse`` ; garde la trace des inhibitions en cours."""

    instances: list[FakeInhibitor] = []

    def __init__(self, _log: Any = None) -> None:
        self.held: list[frozenset[str]] = []
        self.calls: list[set[str]] = []
        self.refuse: set[str] = set()
        self.unavailable = False
        FakeInhibitor.instances.append(self)

    async def acquire(self, wanted: set[str], reason: str) -> tuple[list[Lease], set[str]]:
        assert reason
        self.calls.append(set(wanted))
        if self.unavailable:
            return [], set(wanted)
        covers = frozenset(wanted - self.refuse)

        async def release() -> None:
            self.held.remove(covers)

        self.held.append(covers)
        return [Lease("fake", covers, release)], wanted - covers


class FakeBattery:
    instances: list[FakeBattery] = []

    def __init__(self, on_change: Any, _log: Any = None) -> None:
        self.on_change = on_change
        self.on_battery = False
        self.percentage = 100.0
        self.running = False
        FakeBattery.instances.append(self)

    async def start(self) -> None:
        self.running = True

    async def stop(self) -> None:
        self.running = False


@pytest.fixture
def awake(env, monkeypatch: pytest.MonkeyPatch) -> ModuleManager:
    FakeInhibitor.instances.clear()
    FakeBattery.instances.clear()
    monkeypatch.setattr(keep_awake.KeepAwakeModule, "inhibitor_factory", FakeInhibitor)
    monkeypatch.setattr(keep_awake.KeepAwakeModule, "battery_factory", FakeBattery)
    monkeypatch.setattr(keep_awake, "TICK_SECONDS", 0.05)
    manager = ModuleManager(Registry(), Config.load(), env)
    manager.discover()
    return manager


def _events(manager: ModuleManager) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    manager.event_listeners.append(
        lambda mid, event, data: mid == "keep_awake" and event == "state-changed" and events.append(data)
    )
    return events


def test_start_stop_and_settings(awake: ModuleManager, run) -> None:
    events = _events(awake)

    async def scenario() -> None:
        await awake.start()
        assert awake.is_running("keep_awake")  # actif par défaut, mais rien n'est inhibé
        call = awake.call_action
        inhibitor = FakeInhibitor.instances[-1]
        assert (await call("keep_awake", "status", {}))["active"] is False
        assert inhibitor.held == []

        state = await call("keep_awake", "start", {})  # durée par défaut : jusqu'à nouvel ordre
        assert state["active"] and state["until"] == 0 and state["display"] and not state["lid"]
        assert inhibitor.held == [frozenset({IDLE, SUSPEND})]

        # Écran libre + capot : l'inhibition est refaite avec les nouveaux besoins.
        awake.set_setting("keep_awake", "keep_display_on", False)
        awake.set_setting("keep_awake", "prevent_lid_sleep", True)
        await asyncio.sleep(0.05)
        assert inhibitor.held == [frozenset({SUSPEND, LID})]
        assert (await call("keep_awake", "status", {}))["lid"] is True

        # Relancer pendant une session change seulement la durée.
        state = await call("keep_awake", "start", {"minutes": 30})
        assert 29 * 60 < state["until"] - state["started"] <= 30 * 60 + 1
        assert len(inhibitor.held) == 1

        state = await call("keep_awake", "stop", {})
        assert state["active"] is False and inhibitor.held == []
        assert (await call("keep_awake", "toggle", {}))["active"] is True
        assert (await call("keep_awake", "toggle", {}))["active"] is False

        with pytest.raises(ActionError):
            await call("keep_awake", "start", {"minutes": -1})
        await awake.stop()

    run(scenario())
    assert [e["reason"] for e in events] == ["user", "settings", "settings", "user", "user", "user", "user"]


def test_timer_battery_and_notice(awake: ModuleManager, run) -> None:
    events = _events(awake)

    async def scenario() -> None:
        await awake.start()
        call = awake.call_action
        inhibitor, battery = FakeInhibitor.instances[-1], FakeBattery.instances[-1]
        assert not battery.running  # suivie seulement pendant une session

        await call("keep_awake", "start", {"seconds": 0})  # 0 s = sans fin
        assert (await call("keep_awake", "status", {}))["until"] == 0 and battery.running
        await call("keep_awake", "stop", {})
        assert not battery.running

        await call("keep_awake", "start", {"seconds": 1})
        await asyncio.sleep(0.6)
        assert (await call("keep_awake", "status", {}))["active"] is True
        await asyncio.sleep(0.6)
        assert (await call("keep_awake", "status", {}))["active"] is False
        assert inhibitor.held == []

        # Passage sur batterie sous le seuil (10 % par défaut) : arrêt.
        await call("keep_awake", "start", {})
        battery.on_battery, battery.percentage = True, 40.0
        battery.on_change()
        await asyncio.sleep(0)
        assert (await call("keep_awake", "status", {}))["battery"] == 40
        battery.on_battery, battery.percentage = True, 9.0
        battery.on_change()
        await asyncio.sleep(0.01)
        assert (await call("keep_awake", "status", {}))["active"] is False
        with pytest.raises(ActionError, match="Batterie"):
            await call("keep_awake", "start", {})
        awake.set_setting("keep_awake", "battery_threshold", 0)
        await call("keep_awake", "start", {})
        await call("keep_awake", "stop", {})

        # Le capot refusé par logind : le module tourne, avec un avertissement.
        inhibitor.refuse = {LID}
        awake.set_setting("keep_awake", "prevent_lid_sleep", True)
        await call("keep_awake", "start", {})
        assert "Capot" in awake.state("keep_awake").notice
        await call("keep_awake", "stop", {})
        assert awake.state("keep_awake").notice == ""

        inhibitor.unavailable = True
        with pytest.raises(ActionError, match="Aucun service"):
            await call("keep_awake", "start", {})
        await awake.stop()
        assert not battery.running

    run(scenario())
    assert [e["reason"] for e in events] == ["user", "user", "user", "timer", "user", "battery", "user", "user", "user", "user"]


def test_activate_on_start(awake: ModuleManager, run) -> None:
    awake.set_setting("keep_awake", "activate_on_start", True)
    awake.set_setting("keep_awake", "default_duration", 90)

    async def scenario() -> None:
        await awake.start()
        state = await awake.call_action("keep_awake", "status", {})
        assert state["active"] and state["seconds"] == 90 * 60
        await awake.stop()
        assert FakeInhibitor.instances[-1].held == []  # tout est rendu à l'arrêt

    run(scenario())


# -- bout en bout : vrai démon, faux services d'énergie sur le bus de test ----------------

FAKE = Path(__file__).with_name("fake_power_services.py")


def _fake_state(connection: Gio.DBusConnection) -> dict[str, dict[str, Any]]:
    reply = connection.call_sync("org.saturn.Test", "/org/saturn/Test", "org.saturn.Test1", "State",
                                 None, None, Gio.DBusCallFlags.NONE, 5000, None)
    return json.loads(reply.unpack()[0])


def _wait(predicate, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("condition jamais remplie")


def _action(connection, name: str, params: dict[str, GLib.Variant] | None = None) -> dict[str, Any]:
    (result,) = call_daemon(connection, "CallAction", ("keep_awake", name, params or {}), "(ssa{sv})")
    return result


def _start_fakes(address: str, *args: str, **extra_env: str) -> subprocess.Popen[str]:
    env = dict(os.environ, DBUS_SESSION_BUS_ADDRESS=address, **extra_env)
    return subprocess.Popen([sys.executable, str(FAKE), *args], env=env, stderr=subprocess.PIPE, text=True)


@needs_dbus
@pytest.mark.parametrize(
    ("desktop", "fake_args"),
    [("gnome", []), ("portail", ["--no-gnome", "--portal", "ok"]), ("autres", ["--no-gnome", "--portal", "fail"])],
)
def test_real_inhibitors(bus, monkeypatch: pytest.MonkeyPatch, desktop: str, fake_args: list[str]) -> None:
    address, connection = bus
    monkeypatch.setenv("DBUS_SYSTEM_BUS_ADDRESS", address)  # le bus de test sert aussi de bus système
    fakes = _start_fakes(address, *fake_args)
    daemon = None
    try:
        _wait(lambda: connection.call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "NameHasOwner",
            GLib.Variant("(s)", ("org.saturn.Test",)), None, Gio.DBusCallFlags.NONE, -1, None).unpack()[0])
        daemon = spawn_daemon(address)
        wait_for_owner(connection)
        _wait(lambda: _action(connection, "status") is not None)

        call_daemon(connection, "SetSetting", ("keep_awake", "prevent_lid_sleep", GLib.Variant("b", True)), "(ssv)")
        state = _action(connection, "start", {"minutes": GLib.Variant("x", 15)})
        assert state["active"] and state["lid"] and state["display"]
        fake = _fake_state(connection)
        if desktop == "gnome":
            assert state["backends"] == ["gnome-session", "logind"]
            assert list(fake["gnome"].values()) == [12]  # écran (8) + veille (4)
            assert list(fake["logind"].values()) == ["handle-lid-switch/block"]
        elif desktop == "portail":
            assert state["backends"] == ["portal", "logind"]
            assert list(fake["portal"].values()) == [12]
            assert list(fake["logind"].values()) == ["handle-lid-switch/block"]
        else:
            # Portail en échec, ScreenSaver ne garde que l'écran : veille et capot passent par logind.
            assert state["backends"] == ["screensaver", "logind"]
            assert len(fake["screensaver"]) == 1
            assert list(fake["logind"].values()) == ["handle-lid-switch:sleep/block"]

        # Batterie sous le seuil : saturnd arrête tout seul.
        connection.call_sync("org.saturn.Test", "/org/saturn/Test", "org.saturn.Test1", "SetBattery",
                             GLib.Variant("(bd)", (True, 5.0)), None, Gio.DBusCallFlags.NONE, 5000, None)
        _wait(lambda: not _action(connection, "status")["active"])
        _wait(lambda: not any(_fake_state(connection).values()))

        # Un arrêt brutal du démon rend aussi les inhibitions (descripteur logind fermé par le noyau).
        connection.call_sync("org.saturn.Test", "/org/saturn/Test", "org.saturn.Test1", "SetBattery",
                             GLib.Variant("(bd)", (False, 80.0)), None, Gio.DBusCallFlags.NONE, 5000, None)
        _action(connection, "start")
        assert _fake_state(connection)["logind"]
        daemon.send_signal(signal.SIGKILL)
        daemon.wait()
        _wait(lambda: not _fake_state(connection)["logind"])
        daemon = None
    finally:
        if daemon is not None:
            assert stop_process(daemon) == 0, daemon.stderr.read()
        stop_process(fakes)


@needs_dbus
def test_lid_refused_sets_notice(bus, monkeypatch: pytest.MonkeyPatch) -> None:
    address, connection = bus
    monkeypatch.setenv("DBUS_SYSTEM_BUS_ADDRESS", address)
    fakes = _start_fakes(address, FAKE_LOGIND_REFUSE_LID="1")
    daemon = None
    try:
        _wait(lambda: connection.call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "NameHasOwner",
            GLib.Variant("(s)", ("org.saturn.Test",)), None, Gio.DBusCallFlags.NONE, -1, None).unpack()[0])
        daemon = spawn_daemon(address)
        wait_for_owner(connection)
        call_daemon(connection, "SetSetting", ("keep_awake", "prevent_lid_sleep", GLib.Variant("b", True)), "(ssv)")
        state = _action(connection, "start")
        assert state["active"] and not state["lid"] and state["backends"] == ["gnome-session"]
        (module,) = call_daemon(connection, "GetModule", ("keep_awake",), "(s)")
        assert "Capot" in module["notice"]
        _action(connection, "stop")
        assert not any(_fake_state(connection).values())
    finally:
        if daemon is not None:
            assert stop_process(daemon) == 0, daemon.stderr.read()
        stop_process(fakes)
