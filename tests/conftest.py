from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import sys
import textwrap
import time
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import pytest
from gi.repository import Gio, GLib

from saturn import BUS_NAME, INTERFACE, OBJECT_PATH
from saturn.config import Config
from saturn.desktop import Desktop, Environment, Family, SessionType
from saturn.manager import ModuleManager
from saturn.registry import Registry


@pytest.fixture(autouse=True)
def isolated_xdg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Chaque test écrit dans un dossier temporaire, jamais dans le vrai ~/.config."""
    for variable, name in (
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_STATE_HOME", "state"),
        ("XDG_CACHE_HOME", "cache"),
    ):
        monkeypatch.setenv(variable, str(tmp_path / name))
    return tmp_path


@pytest.fixture
def env() -> Environment:
    return Environment(Desktop.GNOME, Family.GNOME, SessionType.WAYLAND, "GNOME")


@pytest.fixture
def run() -> Callable[[Coroutine[Any, Any, Any]], Any]:
    return asyncio.run


FAKE_MODULES: dict[str, str] = {
    "__init__.py": "",
    "alpha/__init__.py": """
        from saturn.module import Category, ModuleInfo
        from saturn.settings import Setting, SettingType

        MANIFEST = ModuleInfo(
            id="alpha",
            name="Alpha",
            description="Module activé par défaut",
            category=Category.TOOLS,
            entrypoint=".impl:Alpha",
            default_enabled=True,
            settings=(
                Setting("level", SettingType.INT, 3, "Niveau", minimum=0, maximum=10),
                Setting("mode", SettingType.CHOICE, "fast", "Mode", choices=("fast", "slow")),
            ),
        )
    """,
    "alpha/impl.py": """
        from saturn.module import Module, action

        EVENTS = []

        class Alpha(Module):
            async def start(self):
                EVENTS.append("start")

            async def stop(self):
                EVENTS.append("stop")

            def on_setting_changed(self, key, value):
                EVENTS.append(("setting", key, value))

            @action()
            async def echo(self, params):
                self.ctx.emit("echoed", params)
                return {"echo": params.get("text", ""), "level": self.ctx.setting("level")}
    """,
    "beta/__init__.py": """
        from saturn.module import Category, ModuleInfo

        MANIFEST = ModuleInfo(
            id="beta",
            name="Beta",
            description="Module désactivé par défaut",
            category=Category.TOOLS,
            entrypoint=".impl:Beta",
        )
    """,
    "beta/impl.py": """
        from saturn.module import Module

        class Beta(Module):
            pass
    """,
    "gamma/__init__.py": """
        from saturn.module import Category, ModuleInfo, Requirement

        MANIFEST = ModuleInfo(
            id="gamma",
            name="Gamma",
            description="Dépend d'un programme absent",
            category=Category.SYSTEM,
            entrypoint=".impl:Gamma",
            default_enabled=True,
            requirements=(Requirement.binary("saturn-binaire-inexistant", "paquet-fictif"),),
        )
    """,
    "gamma/impl.py": """
        from saturn.module import Module

        class Gamma(Module):
            pass
    """,
    "broken/__init__.py": """
        from saturn.module import Category, ModuleInfo

        MANIFEST = ModuleInfo(
            id="broken",
            name="Broken",
            description="Plante au démarrage",
            category=Category.TOOLS,
            entrypoint=".impl:Broken",
        )
    """,
    "broken/impl.py": """
        from saturn.module import Module

        class Broken(Module):
            async def start(self):
                raise RuntimeError("boum")
    """,
    "nomanifest/__init__.py": "VALUE = 1\n",
}


@pytest.fixture
def fake_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Crée un paquet de modules factices importable sous un nom unique."""
    name = f"fake_modules_{abs(hash(tmp_path)) % 10**8}"
    root = tmp_path / "pkgs" / name
    for relative, source in FAKE_MODULES.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(textwrap.dedent(source))
    monkeypatch.syspath_prepend(str(tmp_path / "pkgs"))
    yield name
    for module_name in [m for m in sys.modules if m == name or m.startswith(name + ".")]:
        del sys.modules[module_name]


@pytest.fixture
def manager(fake_package: str, env: Environment, isolated_xdg: Path) -> ModuleManager:
    mgr = ModuleManager(Registry(fake_package), Config.load(), env)
    mgr.discover()
    return mgr


# -- bus D-Bus privé et vrai démon -------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent


def _unix_sockets_allowed() -> bool:
    try:
        socket.socket(socket.AF_UNIX).close()
    except OSError:
        return False
    return True


needs_dbus = pytest.mark.skipif(
    shutil.which("dbus-daemon") is None or not _unix_sockets_allowed(),
    reason="dbus-daemon absent ou sockets Unix interdits (bac à sable)",
)


@pytest.fixture
def bus(isolated_xdg: Path):
    """Bus de session jetable : ``(adresse, connexion)``."""
    test_bus = Gio.TestDBus.new(Gio.TestDBusFlags.NONE)
    test_bus.up()
    address = test_bus.get_bus_address()
    connection = Gio.DBusConnection.new_for_address_sync(
        address,
        Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
        | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
        None,
        None,
    )
    yield address, connection
    connection.close_sync(None)
    test_bus.down()


def spawn_daemon(address: str, *args: str) -> subprocess.Popen[str]:
    env = dict(os.environ, DBUS_SESSION_BUS_ADDRESS=address, PYTHONPATH=str(ROOT))
    return subprocess.Popen(
        [sys.executable, "-m", "saturn", "--verbose", *args],
        env=env,
        stderr=subprocess.PIPE,
        text=True,
    )


def wait_for_owner(connection: Gio.DBusConnection, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        reply = connection.call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "NameHasOwner", GLib.Variant("(s)", (BUS_NAME,)), None,
            Gio.DBusCallFlags.NONE, -1, None,
        )
        if reply.unpack()[0]:
            return
        time.sleep(0.05)
    raise TimeoutError(f"{BUS_NAME} n'est jamais apparu sur le bus")


def call_daemon(connection, method, args=None, signature=None):
    params = GLib.Variant(signature, args) if signature else None
    reply = connection.call_sync(
        BUS_NAME, OBJECT_PATH, INTERFACE, method, params, None, Gio.DBusCallFlags.NONE, 5000, None
    )
    return reply.unpack()


def stop_process(process: subprocess.Popen[str]) -> int:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    return process.returncode


@pytest.fixture
def daemon(bus):
    """Vrai ``saturnd`` sur le bus privé ; renvoie la connexion du test."""
    address, connection = bus
    process = spawn_daemon(address)
    try:
        wait_for_owner(connection)
        yield connection
    finally:
        assert stop_process(process) == 0, process.stderr.read()
