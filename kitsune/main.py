"""
kitsune.main
~~~~~~~~~~~~~~
Main command-line and application entry point.
"""

from __future__ import annotations
import argparse
import signal
import sys
from PyQt6.QtCore import QTimer

from kitsune import __version__
from kitsune.core.app import KitsuneApp
from kitsune.core.env import Environment


def print_diagnostics() -> None:
    env = Environment.get()
    caps = env.get_capabilities()
    print("=" * 50)
    print(f"Kitsune v{__version__} - Diagnostics Système")
    print("=" * 50)
    print(f"Session       : {caps.session_type.upper()}")
    print(f"Desktop (DE)  : {caps.desktop_environment}")
    print(f"systemd-inhibit: {'Oui' if caps.has_systemd_inhibit else 'Non'}")
    print(f"PipeWire (wpctl): {'Oui' if caps.has_wpctl else 'Non'}")
    print(f"Pulse (pactl) : {'Oui' if caps.has_pactl else 'Non'}")
    print(f"D-Bus (gdbus) : {'Oui' if caps.has_gdbus else 'Non'}")
    print(f"wl-clipboard  : {'Oui' if caps.has_wl_clipboard else 'Non'}")
    print(f"xclip         : {'Oui' if caps.has_xclip else 'Non'}")
    print(f"notify-send   : {'Oui' if caps.has_notify_send else 'Non'}")
    print("=" * 50)


def main() -> int:
    parser = argparse.ArgumentParser(description="Kitsune pour Linux - Boîte à outils modulaire")
    parser.add_argument("--version", action="version", version=f"Kitsune {__version__}")
    parser.add_argument("--diagnostics", action="store_true", help="Affiche les diagnostics environnement/système")
    parser.add_argument("--settings", action="store_true", help="Ouvre directement la fenêtre des paramètres")
    args = parser.parse_args()

    if args.diagnostics:
        print_diagnostics()
        return 0

    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = KitsuneApp(sys.argv)

    # Allow Python to catch UNIX signals like SIGINT
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(500)

    if args.settings:
        app.show_settings()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
