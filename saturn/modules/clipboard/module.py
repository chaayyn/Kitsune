from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from saturn.errors import ActionError
from saturn.module import Module, action
from saturn.modules.clean_url.cleaner import looks_like_url
from saturn.modules.clipboard import backends
from saturn.modules.clipboard.content import MAX_IMAGE_BYTES, ClipContent, from_bytes, URI_LIST
from saturn.modules.clipboard.secrets import secret_reason
from saturn.modules.clipboard.store import ClipboardStore

MAX_PAGE = 500


def _entry_id(params: dict[str, Any]) -> int:
    value = params.get("id")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ActionError("Paramètre « id » (entier) requis")
    return value


class ClipboardModule(Module):
    """Historique du presse-papiers. Le bureau décide d'où viennent les copies (voir backends)."""

    async def start(self) -> None:
        self.store = ClipboardStore(self.ctx.database().connection, self.ctx.data_dir / "images")
        self._tasks: set[asyncio.Task[Any]] = set()
        self._clear_timer: asyncio.TimerHandle | None = None
        self.backend = backends.make_backend(self.ctx, self._on_content)
        self.ctx.log.info("Presse-papiers suivi via %s", self.backend.name)
        await self.backend.start()
        self._prune()

    async def stop(self) -> None:
        if self._clear_timer is not None:
            self._clear_timer.cancel()
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self.backend.stop()

    def on_setting_changed(self, key: str, value: Any) -> None:
        if key in {"max_items", "max_age_days"} and self._prune():
            self.ctx.emit("history-changed", {})

    # -- copies entrantes ---------------------------------------------------------------

    def _on_content(self, content: ClipContent, mimes: tuple[str, ...]) -> None:
        task = asyncio.ensure_future(self._handle(content, mimes))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(self._log_failure)

    def _log_failure(self, task: asyncio.Task[Any]) -> None:
        if not task.cancelled() and task.exception() is not None:
            self.ctx.log.error("Copie non enregistrée", exc_info=task.exception())

    async def _handle(self, content: ClipContent, mimes: tuple[str, ...]) -> None:
        settings = self.ctx.settings
        if settings["ignore_secrets"]:
            reason = secret_reason(content.text, mimes)
            if reason:
                self.ctx.log.info("Copie ignorée : %s", reason)
                self.ctx.emit("ignored", {"reason": reason})
                self._schedule_clear()
                return
        if content.kind == "image" and not settings["store_images"]:
            return
        if content.kind == "files" and not settings["store_files"]:
            return

        if (
            settings["clean_links"]
            and content.kind == "text"
            and looks_like_url(content.text)
            and self.ctx.is_module_running("clean_url")
        ):
            result = await self.ctx.call_module("clean_url", "clean", {"url": content.text})
            if result.get("changed"):
                content = ClipContent("text", text=result["url"], mime=content.mime)
                await self.backend.write(content)
                self.ctx.emit("link-cleaned", {"removed": result.get("removed", [])})

        added = self.store.add(content)
        self._prune()
        self.ctx.emit("history-changed", {"id": added.id, "new": added.new})
        self._schedule_clear()

    def _schedule_clear(self) -> None:
        if self._clear_timer is not None:
            self._clear_timer.cancel()
            self._clear_timer = None
        seconds = self.ctx.settings["clear_after"]
        if seconds <= 0:
            return
        loop = asyncio.get_running_loop()

        def clear() -> None:
            self._clear_timer = None
            task = asyncio.ensure_future(self.backend.clear())
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            task.add_done_callback(self._log_failure)

        self._clear_timer = loop.call_later(seconds, clear)

    def _prune(self) -> int:
        settings = self.ctx.settings
        return self.store.prune(settings["max_items"], settings["max_age_days"])

    # -- actions -------------------------------------------------------------------------

    @action()
    def push(self, params: dict[str, Any]) -> dict[str, Any]:
        """Copie relayée par un client (l'extension GNOME sous GNOME Wayland)."""
        mimes = tuple(str(m) for m in params.get("mimes", []))
        if "text" in params:
            content = from_bytes("text/plain", str(params["text"]).encode())
        elif "image" in params:
            image = bytes(params["image"])
            if len(image) > MAX_IMAGE_BYTES:
                raise ActionError("Image trop grande")
            content = from_bytes(str(params.get("mime", "image/png")), image)
        elif "uris" in params:
            content = from_bytes(URI_LIST, str(params["uris"]).encode())
        else:
            raise ActionError("Paramètre « text », « image » ou « uris » requis")
        if content is not None:
            self._on_content(content, mimes)
        return {"accepted": content is not None}

    @action("list")
    def list_entries(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = min(max(int(params.get("limit", 100)), 1), MAX_PAGE)
        offset = max(int(params.get("offset", 0)), 0)
        items, total = self.store.search(str(params.get("query", "")), limit, offset)
        return {"items": items, "total": total}

    @action()
    def get(self, params: dict[str, Any]) -> dict[str, Any]:
        entry = self.store.get(_entry_id(params))
        if entry is None:
            raise ActionError("Élément introuvable")
        return {"entry": entry}

    @action()
    async def copy(self, params: dict[str, Any]) -> dict[str, Any]:
        entry_id = _entry_id(params)
        content = self.store.content(entry_id)
        if content is None:
            raise ActionError("Élément introuvable")
        await self.backend.write(content)
        self.store.touch(entry_id)
        self.ctx.emit("history-changed", {"id": entry_id, "new": False})
        self._schedule_clear()
        return {"copied": True}

    @action()
    def pin(self, params: dict[str, Any]) -> dict[str, Any]:
        entry_id = _entry_id(params)
        if not self.store.set_pinned(entry_id, bool(params.get("pinned", True))):
            raise ActionError("Élément introuvable")
        self.ctx.emit("history-changed", {"id": entry_id, "new": False})
        return {"pinned": bool(params.get("pinned", True))}

    @action()
    def delete(self, params: dict[str, Any]) -> dict[str, Any]:
        deleted = self.store.delete(_entry_id(params))
        if deleted:
            self.ctx.emit("history-changed", {})
        return {"deleted": deleted}

    @action()
    def clear(self, params: dict[str, Any]) -> dict[str, Any]:
        removed = self.store.clear(keep_pinned=bool(params.get("keep_pinned", True)))
        self.ctx.emit("history-changed", {})
        return {"removed": removed}
