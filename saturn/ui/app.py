"""Point d'entrée de l'interface ``saturn`` : icône, panneau et réglages."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path

from gi.repository import Gio, GLib
from PySide6.QtCore import QAbstractEventDispatcher, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from saturn import __version__
from saturn.ui.backend import Backend
from saturn.ui.client import DaemonClient
from saturn.ui.theme import Theme, apply_palette, load_bundled_fonts

log = logging.getLogger("saturn.ui")

UI_BUS_NAME = "org.saturn.Ui"
#: Nom pris par l'extension GNOME Shell de Saturn quand elle est active.
SHELL_BUS_NAME = "org.saturn.Shell"
UI_OBJECT_PATH = "/org/saturn/Ui"
UI_INTERFACE = "org.saturn.Ui1"
UI_XML = f"""
<node>
  <interface name="{UI_INTERFACE}">
    <method name="TogglePanel"/>
    <method name="ShowPanel"/>
    <method name="OpenSettings"><arg name="id" type="s" direction="in"/></method>
    <method name="OpenClipboard"/>
    <method name="OpenScratchpad"/>
  </interface>
</node>
"""

ROOT = Path(__file__).resolve().parents[2]
QML_DIR = Path(__file__).resolve().parent / "qml"
ICONS_DIR = ROOT / "assets" / "icons"
FONTS_DIR = ROOT / "assets" / "fonts"
QML_PACKAGES_HINT = (
    "sudo apt install qml6-module-qtquick qml6-module-qtquick-controls "
    "qml6-module-qtquick-layouts qml6-module-qtquick-window "
    "qml6-module-qtquick-templates qml6-module-qtqml-workerscript"
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="saturn", description="Interface de Saturn.")
    parser.add_argument("--panel", action="store_true", help="ouvrir le panneau au lancement")
    parser.add_argument(
        "--settings", nargs="?", const="", metavar="MODULE", help="ouvrir les réglages"
    )
    parser.add_argument(
        "--clipboard", action="store_true", help="ouvrir l'historique du presse-papiers"
    )
    parser.add_argument("--scratchpad", action="store_true", help="ouvrir le bloc-notes")
    parser.add_argument("-v", "--verbose", action="store_true", help="journal détaillé")
    parser.add_argument("--version", action="version", version=f"saturn {__version__}")
    return parser.parse_args(argv)


def ensure_glib_dispatch(app: QApplication) -> QTimer | None:
    """Garantit que les rappels Gio (D-Bus) sont traités par la boucle Qt.

    Qt sous Linux tourne normalement sur la boucle GLib par défaut. Si ce n'est
    pas le cas (``QT_NO_GLIB``), on fait tourner le contexte GLib à la main.
    """
    dispatcher = QAbstractEventDispatcher.instance()
    name = dispatcher.metaObject().className() if dispatcher else ""
    if "Glib" in name:
        return None
    log.debug("Boucle Qt sans GLib (%s) : pompage manuel du contexte GLib", name)
    context = GLib.MainContext.default()
    timer = QTimer(app, interval=15)
    timer.timeout.connect(lambda: [context.iteration(False) for _ in range(50) if context.pending()])
    timer.start()
    return timer


def app_icon() -> QIcon:
    icon = QIcon()
    for png in sorted(ICONS_DIR.glob("saturn-*.png")):
        icon.addFile(str(png))
    svg = ICONS_DIR / "saturn-symbolic.svg"
    if svg.exists():
        icon.addFile(str(svg))
    return icon if not icon.isNull() else QIcon.fromTheme("saturn-symbolic")


class SingleInstance:
    """Nom ``org.saturn.Ui`` sur le bus : une seule interface à la fois."""

    def __init__(self, connection: Gio.DBusConnection, backend: Backend) -> None:
        self.connection = connection
        self.backend = backend
        self._registration = 0

    def acquire(self) -> bool:
        reply = self.connection.call_sync(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "RequestName", GLib.Variant("(su)", (UI_BUS_NAME, 4)),  # DO_NOT_QUEUE
            None, Gio.DBusCallFlags.NONE, -1, None,
        )
        if reply.unpack()[0] not in (1, 4):  # PRIMARY_OWNER, ALREADY_OWNER
            return False
        interface = Gio.DBusNodeInfo.new_for_xml(UI_XML).lookup_interface(UI_INTERFACE)
        self._registration = self.connection.register_object(
            UI_OBJECT_PATH, interface, self._on_call, None, None
        )
        return True

    def forward(self, method: str, args: GLib.Variant | None = None) -> None:
        """Transmet la demande à l'interface déjà ouverte."""
        self.connection.call_sync(
            UI_BUS_NAME, UI_OBJECT_PATH, UI_INTERFACE, method, args,
            None, Gio.DBusCallFlags.NONE, 5000, None,
        )

    def _on_call(self, _c, _s, _p, _i, method: str, params: GLib.Variant, invocation) -> None:
        if method == "TogglePanel":
            self.backend.togglePanel()
        elif method == "ShowPanel":
            self.backend.showPanel()
        elif method == "OpenSettings":
            self.backend.openSettings(params.unpack()[0])
        elif method == "OpenClipboard":
            self.backend.openClipboard()
        elif method == "OpenScratchpad":
            self.backend.openScratchpad()
        invocation.return_value(None)


def build_tray(app: QApplication, backend: Backend, icon: QIcon) -> QSystemTrayIcon | None:
    if not QSystemTrayIcon.isSystemTrayAvailable():
        log.warning(
            "Aucune zone de notification détectée. Sous GNOME, activez l'extension "
            "AppIndicator (gnome-shell-extension-appindicator)."
        )
        return None
    tray = QSystemTrayIcon(icon, app)
    tray.setToolTip("Saturn")
    menu = QMenu()
    menu.addAction("Ouvrir Saturn", backend.showPanel)
    menu.addAction("Historique du presse-papiers", backend.openClipboard)
    menu.addAction("Bloc-notes", backend.openScratchpad)
    awake_menu = build_awake_menu(menu, backend)
    menu.addAction("Réglages…", lambda: backend.openSettings(""))
    menu.addSeparator()
    menu.addAction("Quitter", app.quit)
    tray.setContextMenu(menu)
    tray._menu = menu  # garder une référence Python
    tray._awake_menu = awake_menu

    def on_activated(reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            backend.togglePanel()

    def update_tooltip(*_args) -> None:
        modules = backend.modules
        state = f"{modules.activeCount} module(s) actif(s)" if backend.connected else "démon arrêté"
        tray.setToolTip(f"Saturn — {state}")

    tray.activated.connect(on_activated)
    backend.connectedChanged.connect(update_tooltip)
    backend.modules.activeCountChanged.connect(update_tooltip)
    update_tooltip()
    tray.show()
    return tray


#: Durées proposées par le menu « Rester éveillé » (minutes, 0 = sans fin).
AWAKE_DURATIONS = (
    (0, "Jusqu'à nouvel ordre"),
    (15, "15 minutes"),
    (30, "30 minutes"),
    (60, "1 heure"),
    (120, "2 heures"),
    (300, "5 heures"),
)


def build_awake_menu(parent: QMenu, backend: Backend) -> QMenu:
    """Sous-menu « Rester éveillé » : durées cochables et arrêt."""
    menu = parent.addMenu("Rester éveillé")
    group = QActionGroup(menu)
    group.setExclusive(True)
    durations: list[tuple[int, QAction]] = []
    for minutes, text in AWAKE_DURATIONS:
        action_ = menu.addAction(text)
        action_.setCheckable(True)
        group.addAction(action_)
        action_.triggered.connect(lambda _checked=False, m=minutes: backend.startAwake(m))
        durations.append((minutes, action_))
    menu.addSeparator()
    stop = menu.addAction("Arrêter", backend.stopAwake)

    def sync() -> None:
        menu.menuAction().setVisible(backend.awakeAvailable)
        active = backend.awakeActive
        menu.setTitle("Rester éveillé · actif" if active else "Rester éveillé")
        stop.setEnabled(active)
        group.setExclusive(False)  # pour pouvoir tout décocher
        for minutes, action_ in durations:
            action_.setChecked(active and backend.awakeSeconds == minutes * 60)
        group.setExclusive(True)

    backend.awakeChanged.connect(sync)
    sync()
    return menu


def name_has_owner(connection: Gio.DBusConnection, name: str) -> bool:
    reply = connection.call_sync(
        "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
        "NameHasOwner", GLib.Variant("(s)", (name,)), None, Gio.DBusCallFlags.NONE, -1, None,
    )
    return bool(reply.unpack()[0])


def follow_shell_extension(connection: Gio.DBusConnection, tray: QSystemTrayIcon) -> int:
    """Masque l'icône Qt tant que l'extension GNOME de Saturn tient la barre du haut."""

    def appeared(*_args) -> None:
        log.info("Extension GNOME de Saturn active : icône de notification masquée")
        tray.hide()

    def vanished(*_args) -> None:
        tray.show()

    return Gio.bus_watch_name_on_connection(
        connection, SHELL_BUS_NAME, Gio.BusNameWatcherFlags.NONE, appeared, vanished
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    app = QApplication(sys.argv[:1])
    app.setApplicationName("saturn")
    app.setApplicationDisplayName("Saturn")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("saturn")
    app.setQuitOnLastWindowClosed(False)
    icon = app_icon()
    app.setWindowIcon(icon)
    ensure_glib_dispatch(app)

    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    client = DaemonClient(connection)
    backend = Backend(client)

    instance = SingleInstance(connection, backend)
    if not instance.acquire():
        if args.clipboard:
            instance.forward("OpenClipboard")
        elif args.scratchpad:
            instance.forward("OpenScratchpad")
        elif args.settings is not None:
            instance.forward("OpenSettings", GLib.Variant("(s)", (args.settings,)))
        else:
            instance.forward("ShowPanel" if args.panel else "TogglePanel")
        log.info("Saturn est déjà ouvert : demande transmise.")
        return 0

    bundled = load_bundled_fonts(FONTS_DIR)
    theme = Theme(app)
    apply_palette(app)
    if theme.missing_fonts:
        log.warning(
            "Polices absentes : %s (repli sur %s / %s)",
            ", ".join(theme.missing_fonts), theme.displayFont, theme.monoFont,
        )
    log.debug("Polices livrées chargées : %s", bundled)

    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("Saturn", backend)
    engine.rootContext().setContextProperty("Theme", theme)
    engine.rootContext().setContextProperty("SaturnIcon", QUrl.fromLocalFile(str(ICONS_DIR / "saturn-symbolic.svg")))
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    if not engine.rootObjects():
        log.error("Interface QML introuvable ou modules QML manquants. Essayez : %s", QML_PACKAGES_HINT)
        return 1

    tray = build_tray(app, backend, icon)
    if tray is not None:
        follow_shell_extension(connection, tray)
    # Sans icône ni extension GNOME, le panneau est le seul point d'entrée : on l'ouvre.
    requested = args.settings is not None or args.clipboard or args.scratchpad
    if args.panel or (tray is None and not requested and not name_has_owner(connection, SHELL_BUS_NAME)):
        QTimer.singleShot(0, backend.showPanel)
    if args.settings is not None:
        QTimer.singleShot(0, lambda: backend.openSettings(args.settings))
    if args.clipboard:
        # Laisse le temps à la connexion au démon d'aboutir avant de chercher.
        QTimer.singleShot(300, backend.openClipboard)
    if args.scratchpad:
        QTimer.singleShot(300, backend.openScratchpad)

    # Ctrl+C dans le terminal : laisser Python voir le signal malgré la boucle Qt.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal_timer = QTimer(app, interval=250)
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start()

    code = app.exec()
    client.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
