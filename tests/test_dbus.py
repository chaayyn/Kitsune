"""Test de bout en bout : vrai ``saturnd`` sur un bus de session privé."""

from __future__ import annotations

import pytest
from gi.repository import Gio, GLib

from saturn import BUS_NAME, INTERFACE, OBJECT_PATH, __version__
from tests.conftest import call_daemon as _call, needs_dbus, spawn_daemon as _spawn

pytestmark = needs_dbus


def test_list_and_toggle_modules(daemon) -> None:
    (modules,) = _call(daemon, "ListModules")
    by_id = {module["id"]: module for module in modules}
    assert by_id["clean_url"]["enabled"] is True
    assert by_id["clean_url"]["running"] is True
    assert by_id["clean_url"]["actions"] == ["clean"]

    (state,) = _call(daemon, "SetModuleEnabled", ("clean_url", False), "(sb)")
    assert state["enabled"] is False and state["running"] is False

    with pytest.raises(GLib.Error, match="ModuleNotRunning"):
        _call(daemon, "CallAction", ("clean_url", "clean", {}), "(ssa{sv})")

    (state,) = _call(daemon, "SetModuleEnabled", ("clean_url", True), "(sb)")
    assert state["running"] is True


def test_settings_and_actions(daemon) -> None:
    (schema,) = _call(daemon, "GetSettingsSchema", ("clean_url",), "(s)")
    assert [entry["key"] for entry in schema] == ["extra_params", "keep_params"]

    _call(daemon, "SetSetting", ("clean_url", "extra_params", GLib.Variant("as", ["ref"])), "(ssv)")
    (settings,) = _call(daemon, "GetSettings", ("clean_url",), "(s)")
    assert settings["extra_params"] == ["ref"]

    with pytest.raises(GLib.Error, match="InvalidSetting"):
        _call(daemon, "SetSetting", ("clean_url", "extra_params", GLib.Variant("s", "x")), "(ssv)")

    params = {"url": GLib.Variant("s", "https://a.example/?ref=1&utm_source=2&id=3")}
    (result,) = _call(daemon, "CallAction", ("clean_url", "clean", params), "(ssa{sv})")
    assert result == {"url": "https://a.example/?id=3", "changed": True, "removed": ["ref", "utm_source"]}

    with pytest.raises(GLib.Error, match="UnknownModule"):
        _call(daemon, "GetModule", ("nope",), "(s)")


def test_environment_and_version(daemon) -> None:
    (environment,) = _call(daemon, "GetEnvironment")
    assert set(environment) == {"desktop", "family", "session", "raw_desktop"}
    reply = daemon.call_sync(
        BUS_NAME, OBJECT_PATH, "org.freedesktop.DBus.Properties", "Get",
        GLib.Variant("(ss)", (INTERFACE, "Version")), None, Gio.DBusCallFlags.NONE, 5000, None,
    )
    assert reply.unpack() == (__version__,)


def test_second_instance_refuses_to_start(daemon, bus) -> None:
    address, _ = bus
    second = _spawn(address)
    assert second.wait(timeout=10) == 1
    assert "une autre instance" in second.stderr.read()
