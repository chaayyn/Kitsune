"""Pont QML ↔ D-Bus : modèles Qt, conversions, et Backend face à un vrai saturnd."""

from __future__ import annotations

import os
import time
from collections.abc import Callable

import pytest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
# Un thème de plateforme (qt5ct, gtk3…) peut ouvrir une connexion Gio au bus de
# session : Gio.TestDBus.down() attendrait alors 30 s qu'elle disparaisse.
os.environ["QT_QPA_PLATFORMTHEME"] = ""

from gi.repository import GLib  # noqa: E402
from PySide6.QtCore import QCoreApplication, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from saturn.ui.backend import Backend, coerce_setting  # noqa: E402
from saturn.ui.client import DaemonClient  # noqa: E402
from saturn.ui.models import ModuleListModel, SettingsModel, module_status  # noqa: E402
from tests.conftest import needs_dbus, spawn_daemon, stop_process, wait_for_owner  # noqa: E402


@pytest.fixture(scope="session")
def qt_app() -> QGuiApplication:
    return QGuiApplication.instance() or QGuiApplication([])


def pump(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    """Fait tourner Qt et GLib jusqu'à ce que ``predicate`` soit vrai."""
    context = GLib.MainContext.default()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        while context.pending():
            context.iteration(False)
        if predicate():
            return
        time.sleep(0.01)
    raise TimeoutError("condition jamais remplie")


def roles(model) -> dict[str, int]:
    return {bytes(name).decode(): role for role, name in model.roleNames().items()}


def module(id_: str, category: str, **extra) -> dict:
    base = {
        "id": id_, "name": id_.title(), "description": "", "category": category,
        "enabled": True, "running": True, "available": True, "missing": [], "error": "",
        "actions": [],
    }
    return base | extra


# -- modèles ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ({"enabled": True, "running": True}, "running"),
        ({"enabled": False, "running": False}, "off"),
        ({"enabled": True, "running": False, "error": "boum"}, "error"),
        ({"enabled": True, "running": False}, "starting"),
        ({"enabled": True, "running": False, "available": False}, "unavailable"),
        ({"enabled": False, "available": False}, "unavailable"),
    ],
)
def test_module_status(state, expected) -> None:
    assert module_status(state) == expected


def test_module_model_sorts_by_category_and_updates(qt_app) -> None:
    model = ModuleListModel()
    model.reset([module("zeta", "tools"), module("clean", "clipboard"), module("alpha", "tools")])

    assert [row["moduleId"] for row in model.rows()] == ["clean", "alpha", "zeta"]
    assert model.rows()[0]["categoryLabel"] == "Presse-papiers"
    assert model.activeCount == 3

    changes = []
    model.dataChanged.connect(lambda first, *_: changes.append(first.row()))
    model.update(module("alpha", "tools", enabled=False, running=False))
    assert changes == [1]
    assert model.module("alpha")["status"] == "off"
    assert model.activeCount == 2

    model.update(module("beta", "tools"))  # nouveau : inséré à sa place
    assert [row["moduleId"] for row in model.rows()] == ["clean", "alpha", "beta", "zeta"]

    model.set_pending("beta", True)
    index = model.index(model.row_of("beta"), 0)
    assert model.data(index, roles(model)["pending"]) is True
    assert model.data(index, roles(model)["isEnabled"]) is True
    assert model.data(model.index(99, 0), roles(model)["name"]) is None


def test_settings_model_tracks_defaults(qt_app) -> None:
    model = SettingsModel()
    schema = [
        {"key": "extra", "type": "string_list", "signature": "as", "label": "Extra", "default": []},
        {"key": "level", "type": "int", "signature": "x", "label": "Niveau", "default": 3,
         "minimum": 0.0, "maximum": 10.0},
    ]
    model.load(schema, {"extra": ["ref"], "level": 3})

    assert model.count == 2
    assert model.get(0)["isDefault"] is False
    assert model.get(1)["isDefault"] is True
    assert model.get(1)["hasMaximum"] is True and model.get(1)["maximum"] == 10.0
    assert model.signature("level") == "x"

    model.set_value("extra", [])
    assert model.get(0)["isDefault"] is True
    assert model.data(model.index(0, 0), roles(model)["value"]) == []


@pytest.mark.parametrize(
    ("signature", "value", "expected"),
    [
        ("b", 1, True),
        ("x", 4.0, 4),
        ("d", 2, 2.0),
        ("s", 12, "12"),
        ("as", ["a", 3], ["a", "3"]),
        ("as", None, []),
    ],
)
def test_coerce_setting(signature, value, expected) -> None:
    assert coerce_setting(signature, value) == expected


@pytest.mark.parametrize(("signature", "value"), [("x", 2.5), ("as", "texte"), ("as", 3)])
def test_coerce_setting_rejects_bad_values(signature, value) -> None:
    with pytest.raises(ValueError):
        coerce_setting(signature, value)


# -- Backend face au vrai démon -----------------------------------------------------------


@needs_dbus
def test_backend_follows_the_daemon(qt_app, bus) -> None:
    address, connection = bus
    client = DaemonClient(connection)
    backend = Backend(client)
    notes: list[tuple[str, str]] = []
    backend.notify.connect(lambda message, level: notes.append((message, level)))

    assert not backend.connected and backend.modules.count == 0

    process = spawn_daemon(address)
    try:
        wait_for_owner(connection)
        pump(lambda: backend.connected and backend.modules.count > 0 and backend.version != "")
        assert backend.modules.module("clean_url")["status"] == "running"
        assert backend.desktop  # environnement relayé

        # Interrupteur : vraie désactivation côté démon, état reflété dans le modèle.
        backend.setModuleEnabled("clean_url", False)
        assert backend.modules.module("clean_url")["pending"] is True
        pump(lambda: backend.modules.module("clean_url")["status"] == "off")
        assert backend.modules.module("clean_url")["pending"] is False
        backend.setModuleEnabled("clean_url", True)
        pump(lambda: backend.modules.module("clean_url")["status"] == "running")

        # Réglages chargés depuis le schéma, modifiés, puis mis à jour par signal.
        backend.selectModule("clean_url")
        assert backend.currentModuleId == "clean_url"
        pump(lambda: backend.settings.count == 2)
        backend.setSetting("extra_params", ["ref_*"])
        pump(lambda: backend.settings.value("extra_params") == ["ref_*"])
        assert backend.currentModule["name"] == "Clean URL"

        backend.resetSetting("extra_params")
        pump(lambda: backend.settings.value("extra_params") == [])

        # Valeur invalide : refusée avant l'envoi…
        backend.setSetting("extra_params", "pas une liste")
        assert notes[-1] == ("'pas une liste' n'est pas une liste", "error")
        # … ou par le démon, et l'erreur remonte à l'interface.
        client.set_setting("clean_url", "extra_params", "s", "x", None, backend._report)
        pump(lambda: any("liste de textes" in message for message, _ in notes))
        assert backend.settings.value("extra_params") == []
    finally:
        assert stop_process(process) == 0, process.stderr.read()

    # Démon arrêté : l'interface passe hors ligne et vide ses modèles.
    pump(lambda: not backend.connected)
    assert backend.modules.count == 0
    client.close()


@needs_dbus
def test_start_daemon_from_the_ui(qt_app, bus, monkeypatch) -> None:
    address, connection = bus
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", address)
    client = DaemonClient(connection)
    backend = Backend(client)

    backend.startDaemon()
    assert backend.starting
    try:
        pump(lambda: backend.connected, timeout=10)
        assert not backend.starting
        pump(lambda: backend.modules.count > 0)
    finally:
        connection.call_sync(
            "org.saturn.Daemon", "/org/saturn/Daemon", "org.freedesktop.DBus.Peer", "Ping",
            None, None, 0, -1, None,
        )
        # Arrêt propre du démon lancé en arrière-plan.
        pid = connection.call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "GetConnectionUnixProcessID", GLib.Variant("(s)", ("org.saturn.Daemon",)),
            None, 0, -1, None,
        ).unpack()[0]
        os.kill(pid, 15)
        pump(lambda: not backend.connected)
        client.close()


def test_roles_do_not_clash_with_qml_item_properties(qt_app) -> None:
    # « enabled », « visible »… sont des propriétés finales d'Item en QML.
    reserved = {"enabled", "visible", "opacity", "state", "width", "height", "x", "y"}
    for model in (ModuleListModel(), SettingsModel()):
        assert not reserved & set(roles(model))
    assert Qt.ItemDataRole.UserRole + 1 in ModuleListModel().roleNames()


def test_font_selection(qt_app) -> None:
    from saturn.ui.app import FONTS_DIR
    from saturn.ui.theme import DISPLAY_FONTS, load_bundled_fonts, pick_family

    assert pick_family(("A", "B"), {"B"}) == "B"
    assert pick_family(("A", "B"), set()) == "B"  # dernier recours
    assert pick_family(("A", "B"), {"A", "C"}, override="C") == "C"
    assert pick_family(("A", "B"), {"A"}, override="absente") == "A"
    if FONTS_DIR.is_dir():
        assert "Space Grotesk" in load_bundled_fonts(FONTS_DIR)
        assert DISPLAY_FONTS[0] == "Space Grotesk"


@needs_dbus
def test_tray_icon_hides_while_gnome_extension_runs(qt_app, bus) -> None:
    from gi.repository import Gio

    from saturn.ui.app import SHELL_BUS_NAME, follow_shell_extension, name_has_owner

    _address, connection = bus

    class FakeTray:
        visible = True

        def hide(self) -> None:
            self.visible = False

        def show(self) -> None:
            self.visible = True

    tray = FakeTray()
    watch = follow_shell_extension(connection, tray)
    try:
        owner = Gio.bus_own_name_on_connection(
            connection, SHELL_BUS_NAME, Gio.BusNameOwnerFlags.NONE, None, None
        )
        pump(lambda: not tray.visible)
        assert name_has_owner(connection, SHELL_BUS_NAME)
        Gio.bus_unown_name(owner)
        pump(lambda: tray.visible)
    finally:
        Gio.bus_unwatch_name(watch)


def test_clipboard_model_labels(qt_app) -> None:
    from saturn.ui.models import ClipboardModel, human_size, relative_time

    now = 1_000_000.0
    assert relative_time(now - 5, now) == "à l'instant"
    assert relative_time(now - 600, now) == "il y a 10 min"
    assert relative_time(now - 7200, now) == "il y a 2 h"
    assert relative_time(now - 90000, now) == "hier"
    assert human_size("text", 512) == "512 o"
    assert human_size("image", 2048) == "2,0 Ko"
    assert human_size("files", 1) == "1 fichier"

    model = ClipboardModel()
    revision = model.revision
    model.load([
        {"id": 3, "kind": "image", "preview": "Image PNG", "image": "/tmp/a.png", "size": 10, "used": now},
        {"id": 2, "kind": "text", "preview": "Bonjour", "text": "Bonjour", "pinned": True, "used": now - 600},
    ], now=now)
    assert model.revision == revision + 1
    assert model.get(0)["imageUrl"] == "file:///tmp/a.png"
    assert model.get(1)["timeLabel"] == "il y a 10 min" and model.get(1)["pinned"] is True


@needs_dbus
def test_backend_clipboard_flow(qt_app, bus, monkeypatch) -> None:
    from gi.repository import GLib as G

    address, connection = bus
    client = DaemonClient(connection)
    backend = Backend(client)
    writes: list[dict] = []
    previous = client.on_module_event

    def on_event(module_id, event, data):
        if event == "write":
            writes.append(data)
        previous(module_id, event, data)

    client.on_module_event = on_event
    process = spawn_daemon(address)
    try:
        wait_for_owner(connection)
        pump(lambda: backend.connected and backend.modules.count >= 2)
        assert backend.clipboardInstalled and not backend.clipboardActive

        backend.setClipboardVisible(True)
        backend.setModuleEnabled("clipboard", True)
        pump(lambda: backend.clipboardActive)
        # Bureau GNOME simulé sans l'extension : le module le signale.
        pump(lambda: "extension GNOME" in backend.clipboardNotice)

        push = G.Variant("(ssa{sv})", ("clipboard", "push", {"text": G.Variant("s", "Copié ailleurs")}))
        connection.call_sync("org.saturn.Daemon", "/org/saturn/Daemon", "org.saturn.Daemon1",
                             "CallAction", push, None, 0, -1, None)
        pump(lambda: backend.clipboard.count == 1)  # rechargé par l'évènement history-changed
        assert backend.clipboardTotal == 1
        entry = backend.clipboard.get(0)
        assert entry["text"] == "Copié ailleurs"

        copied = []
        backend.clipboardCopied.connect(lambda: copied.append(True))
        backend.copyEntry(entry["entryId"])
        pump(lambda: copied and writes)
        assert writes[-1] == {"text": "Copié ailleurs"}  # relayé à l'extension GNOME

        backend.pinEntry(entry["entryId"], True)
        pump(lambda: backend.clipboard.get(0).get("pinned") is True)
        backend.searchClipboard("introuvable")
        pump(lambda: backend.clipboard.count == 0)
        backend.searchClipboard("")
        pump(lambda: backend.clipboard.count == 1)
        backend.deleteEntry(entry["entryId"])
        pump(lambda: backend.clipboard.count == 0)
    finally:
        assert stop_process(process) == 0, process.stderr.read()
    client.close()
