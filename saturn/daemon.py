"""Point d'entrée de ``saturnd``.

La boucle asyncio tourne sur la boucle principale GLib (``gi.events``), ce qui
permet aux modules d'utiliser ``async``/``await`` et Gio (D-Bus, portails XDG)
dans le même thread.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from gi.events import GLibEventLoop
from gi.repository import GLib

from saturn import BUS_NAME, __version__
from saturn.config import Config
from saturn.dbus_service import BusNameTakenError, DBusService
from saturn.desktop import detect
from saturn.manager import ModuleManager
from saturn.registry import Registry

log = logging.getLogger("saturn")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="saturnd", description="Démon de Saturn.")
    parser.add_argument(
        "--replace", action="store_true", help="remplacer une instance déjà lancée"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="journal détaillé")
    parser.add_argument("--version", action="version", version=f"saturnd {__version__}")
    return parser.parse_args(argv)


async def run(args: argparse.Namespace) -> int:
    env = detect()
    log.info(
        "Saturn %s — bureau %s (%s), session %s",
        __version__,
        env.desktop,
        env.family,
        env.session,
    )

    manager = ModuleManager(Registry(), Config.load(), env)
    manager.discover()

    service = DBusService(manager, env, replace=args.replace)
    try:
        await service.start()
    except BusNameTakenError as exc:
        log.error("%s", exc)
        return 1

    stop = asyncio.Event()
    service.on_name_lost = stop.set
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    try:
        await manager.start()
        log.info("Prêt sur %s", BUS_NAME)
        await stop.wait()
    finally:
        log.info("Arrêt…")
        service.stop()
        await manager.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
    )
    return asyncio.run(run(args), loop_factory=lambda: GLibEventLoop(GLib.MainContext.default()))


if __name__ == "__main__":
    raise SystemExit(main())
