from __future__ import annotations

import asyncio
from typing import Any

from saturn.errors import ActionError
from saturn.module import Module, action
from saturn.modules.color_picker.colors import (
    format_color,
    parse_hex,
    to_hex,
    to_hsl_text,
    to_rgb_text,
)
from saturn.modules.color_picker.copier import copy_text
from saturn.modules.color_picker.pickers import PickCancelled, PickUnavailable, pick_color
from saturn.modules.color_picker.store import ColorStore

FORMATS = ("hex", "rgb", "hsl")


def _hex_param(params: dict[str, Any]) -> str:
    try:
        return to_hex(parse_hex(str(params.get("hex", ""))))
    except ValueError as exc:
        raise ActionError(str(exc)) from exc


def describe(hex_value: str) -> dict[str, Any]:
    rgb = parse_hex(hex_value)
    return {"hex": hex_value, "rgb": to_rgb_text(rgb), "hsl": to_hsl_text(rgb)}


class ColorPickerModule(Module):
    """Prélèvement asynchrone : ``pick`` rend la main tout de suite, le résultat
    arrive par l'évènement ``picked`` (on peut viser longtemps)."""

    # Remplaçables dans les tests.
    picker: Any = staticmethod(pick_color)
    copier: Any = staticmethod(copy_text)

    async def start(self) -> None:
        self.store = ColorStore(self.ctx.database().connection)
        self._task: asyncio.Task[None] | None = None

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def on_setting_changed(self, key: str, value: Any) -> None:
        if key == "history_size":
            with self.store.db:
                self.store.trim(int(value))
            self.ctx.emit("history-changed", {})

    # -- actions ------------------------------------------------------------------------

    @action()
    def pick(self, _params: dict[str, Any]) -> dict[str, Any]:
        if self._task is not None and not self._task.done():
            return {"started": False}
        self._task = asyncio.get_running_loop().create_task(self._pick())
        return {"started": True}

    @action("list")
    def list_colors(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {"colors": [describe(row["hex"]) | {"picked": row["picked"]} for row in self.store.list()]}

    @action()
    async def copy(self, params: dict[str, Any]) -> dict[str, Any]:
        hex_value = _hex_param(params)
        fmt = str(params.get("format") or self.ctx.setting("copy_format"))
        if fmt not in FORMATS:
            fmt = "hex"
        text = format_color(parse_hex(hex_value), fmt)
        copied = await self.copier(self.ctx, text)
        if not copied:
            raise ActionError("Impossible d'écrire le presse-papiers sur ce bureau")
        return {"text": text, "copied": True}

    @action()
    def delete(self, params: dict[str, Any]) -> dict[str, Any]:
        deleted = self.store.delete(_hex_param(params))
        if deleted:
            self.ctx.emit("history-changed", {})
        return {"deleted": deleted}

    @action()
    def clear(self, _params: dict[str, Any]) -> dict[str, Any]:
        self.store.clear()
        self.ctx.emit("history-changed", {})
        return {}

    # -- prélèvement ----------------------------------------------------------------------

    async def _pick(self) -> None:
        try:
            rgb = await self.picker(self.ctx.log)
        except PickCancelled:
            self.ctx.emit("picked", {"status": "cancelled"})
            return
        except PickUnavailable as exc:
            self.ctx.set_notice(str(exc))
            self.ctx.emit("picked", {"status": "error", "message": str(exc)})
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.ctx.log.warning("Prélèvement impossible : %s", exc)
            self.ctx.emit("picked", {"status": "error", "message": f"Prélèvement impossible : {exc}"})
            return

        self.ctx.set_notice("")
        hex_value = to_hex(rgb)
        self.store.add(hex_value, int(self.ctx.setting("history_size")))
        fmt = str(self.ctx.setting("copy_format"))
        text = format_color(rgb, fmt)
        copied = fmt != "none" and await self.copier(self.ctx, text)
        self.ctx.emit("picked", {"status": "ok", **describe(hex_value), "text": text, "copied": bool(copied)})
        self.ctx.emit("history-changed", {})
