"""Accès au presse-papiers selon le bureau.

* GNOME Wayland : seule l'extension GNOME Shell peut lire le presse-papiers.
  Elle pousse chaque copie au démon (action ``push``) et applique les écritures
  qu'il lui envoie (évènement ``write``).
* KDE, wlroots… (Wayland) : ``wl-paste --watch`` / ``wl-copy`` (protocole data-control).
* X11 : Gtk 3 (signal ``owner-change``), importé seulement dans ce cas.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from saturn.desktop import Family
from saturn.modules.clipboard.content import (
    URI_LIST,
    ClipContent,
    choose_mime,
    from_bytes,
    to_uri_list,
)

if TYPE_CHECKING:
    from saturn.module import ModuleContext

log = logging.getLogger(__name__)

ContentCallback = Callable[[ClipContent, tuple[str, ...]], None]

SHELL_BUS_NAME = "org.saturn.Shell"
COMMAND_TIMEOUT = 5.0


class ClipboardBackend:
    """Interface commune : suivre les copies, écrire et vider le presse-papiers."""

    name = "base"

    def __init__(self, ctx: ModuleContext, on_content: ContentCallback) -> None:
        self.ctx = ctx
        self.on_content = on_content

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def write(self, content: ClipContent) -> None:
        raise NotImplementedError

    async def clear(self) -> None:
        raise NotImplementedError

    def _wanted_mime(self, mimes: list[str]) -> str | None:
        settings = self.ctx.settings
        return choose_mime(mimes, settings["store_images"], settings["store_files"])


# -- GNOME : l'extension relaie --------------------------------------------------------


class ShellBackend(ClipboardBackend):
    name = "gnome-shell"

    async def start(self) -> None:
        from gi.repository import Gio

        self._watch = Gio.bus_watch_name(
            Gio.BusType.SESSION,
            SHELL_BUS_NAME,
            Gio.BusNameWatcherFlags.NONE,
            lambda *_: self.ctx.set_notice(""),
            lambda *_: self.ctx.set_notice(
                "L'extension GNOME de Saturn est nécessaire pour suivre le presse-papiers "
                "(scripts/install.sh, puis reconnexion)."
            ),
        )

    async def stop(self) -> None:
        from gi.repository import Gio

        if getattr(self, "_watch", 0):
            Gio.bus_unwatch_name(self._watch)
            self._watch = 0

    def push(self, content: ClipContent, mimes: tuple[str, ...]) -> None:
        self.on_content(content, mimes)

    async def write(self, content: ClipContent) -> None:
        match content.kind:
            case "text":
                self.ctx.emit("write", {"text": content.text})
            case "image":
                self.ctx.emit("write", {"image": content.image, "mime": content.mime})
            case "files":
                self.ctx.emit("write", {"uris": to_uri_list(content.files)})

    async def clear(self) -> None:
        self.ctx.emit("write", {"clear": True})


# -- Wayland hors GNOME : wl-clipboard -------------------------------------------------


async def _run(*argv: str, data: bytes | None = None) -> bytes:
    """Lance une commande courte et renvoie sa sortie (lève en cas d'échec)."""
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE if data is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(data), COMMAND_TIMEOUT)
    except TimeoutError:
        process.kill()
        raise
    if process.returncode != 0:
        raise RuntimeError(f"{argv[0]} : {err.decode(errors='replace').strip() or process.returncode}")
    return out


async def _feed(*argv: str, data: bytes) -> None:
    """Comme :func:`_run`, pour wl-copy qui reste en arrière-plan pour servir la sélection :
    on ne garde aucun tube ouvert vers lui, sinon on attendrait sa fin indéfiniment."""
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    assert process.stdin is not None
    process.stdin.write(data)
    await process.stdin.drain()
    process.stdin.close()
    await asyncio.wait_for(process.wait(), COMMAND_TIMEOUT)


class WlClipboardBackend(ClipboardBackend):
    name = "wl-clipboard"

    def __init__(self, ctx: ModuleContext, on_content: ContentCallback) -> None:
        super().__init__(ctx, on_content)
        self._process: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task[None] | None = None
        self._stopping = False

    async def start(self) -> None:
        # wl-paste lance « echo » à chaque changement : une ligne = une nouvelle copie.
        self._process = await asyncio.create_subprocess_exec(
            "wl-paste", "--watch", "echo", "changed",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader = asyncio.create_task(self._read())

    async def stop(self) -> None:
        self._stopping = True
        if self._process is not None and self._process.returncode is None:
            self._process.terminate()
            with contextlib.suppress(TimeoutError, ProcessLookupError):
                await asyncio.wait_for(self._process.wait(), COMMAND_TIMEOUT)
        if self._reader is not None:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader

    async def _read(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        while line := await self._process.stdout.readline():
            if line.strip():
                try:
                    await self._capture()
                except Exception:
                    log.exception("Lecture du presse-papiers impossible")
        if not self._stopping:
            assert self._process.stderr is not None
            error = (await self._process.stderr.read()).decode(errors="replace").strip()
            log.error("wl-paste s'est arrêté : %s", error or self._process.returncode)
            self.ctx.set_notice(f"Suivi du presse-papiers interrompu (wl-paste : {error or 'arrêt'}).")

    async def _capture(self) -> None:
        mimes = (await _run("wl-paste", "--list-types")).decode(errors="replace").split()
        mime = self._wanted_mime(mimes)
        if mime is None:
            return
        data = await _run("wl-paste", "--no-newline", "--type", mime)
        content = from_bytes(mime, data)
        if content is not None:
            self.on_content(content, tuple(mimes))

    async def write(self, content: ClipContent) -> None:
        match content.kind:
            case "text":
                await _feed("wl-copy", "--type", "text/plain;charset=utf-8", data=content.text.encode())
            case "image":
                await _feed("wl-copy", "--type", content.mime, data=content.image)
            case "files":
                await _feed("wl-copy", "--type", URI_LIST, data=to_uri_list(content.files).encode())

    async def clear(self) -> None:
        await _run("wl-copy", "--clear")


# -- X11 : Gtk 3 ---------------------------------------------------------------------------


class X11Backend(ClipboardBackend):
    name = "x11"

    async def start(self) -> None:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, Gtk

        if not Gtk.init_check(None)[0]:
            raise RuntimeError("Gtk ne peut pas ouvrir l'affichage X11")
        self._Gdk = Gdk
        self._clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self._handler = self._clipboard.connect("owner-change", self._on_owner_change)
        # Envoie tout de suite l'abonnement XFixes au serveur X : sans ça, une copie
        # faite juste après le démarrage passerait inaperçue.
        self._clipboard.get_display().flush()

    async def stop(self) -> None:
        if getattr(self, "_handler", 0):
            self._clipboard.disconnect(self._handler)
            self._handler = 0

    def _on_owner_change(self, clipboard: Any, _event: Any) -> None:
        clipboard.request_targets(self._on_targets)

    def _on_targets(self, clipboard: Any, atoms: Any, *_args: Any) -> None:
        mimes = [atom.name() for atom in atoms or []]
        mime = self._wanted_mime(mimes)
        if mime is None:
            return
        found = tuple(mimes)
        if mime == URI_LIST:
            clipboard.request_uris(lambda _c, uris: self._deliver(URI_LIST, "\r\n".join(uris or []).encode(), found))
        elif mime.startswith("image/"):
            clipboard.request_image(lambda _c, pixbuf: self._deliver_image(pixbuf, found))
        else:
            clipboard.request_text(lambda _c, text: self._deliver("text/plain", (text or "").encode(), found))

    def _deliver_image(self, pixbuf: Any, mimes: tuple[str, ...]) -> None:
        if pixbuf is None:
            return
        ok, data = pixbuf.save_to_bufferv("png", [], [])
        if ok:
            self._deliver("image/png", bytes(data), mimes)

    def _deliver(self, mime: str, data: bytes, mimes: tuple[str, ...]) -> None:
        content = from_bytes(mime, data)
        if content is not None:
            self.on_content(content, mimes)

    async def write(self, content: ClipContent) -> None:
        match content.kind:
            case "text":
                self._clipboard.set_text(content.text, -1)
            case "image":
                from gi.repository import GdkPixbuf

                loader = GdkPixbuf.PixbufLoader()
                loader.write(content.image)
                loader.close()
                self._clipboard.set_image(loader.get_pixbuf())
            case "files":
                # Gtk 3 n'offre pas d'écriture simple de text/uri-list : on copie les chemins.
                self._clipboard.set_text("\n".join(content.files), -1)
        self._clipboard.store()

    async def clear(self) -> None:
        self._clipboard.set_text("", 0)


def make_backend(ctx: ModuleContext, on_content: ContentCallback) -> ClipboardBackend:
    env = ctx.env
    if env.is_x11:
        return X11Backend(ctx, on_content)
    if env.is_wayland and env.family is Family.GNOME:
        return ShellBackend(ctx, on_content)
    if env.is_wayland:
        return WlClipboardBackend(ctx, on_content)
    raise RuntimeError(f"Session {env.session} non prise en charge pour le presse-papiers")
