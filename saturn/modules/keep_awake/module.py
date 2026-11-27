from __future__ import annotations

import asyncio
import time
from typing import Any

from saturn.errors import ActionError
from saturn.module import Module, action
from saturn.modules.keep_awake.inhibitors import (
    IDLE,
    LID,
    SUSPEND,
    BatteryWatcher,
    DBusInhibitor,
    Inhibitor,
    Lease,
    UPowerWatcher,
)

REASON = "Mode « Rester éveillé » de Saturn"

#: Le minuteur se recale sur l'horloge murale à cet intervalle : après une mise
#: en veille forcée, l'heure de fin reste juste.
TICK_SECONDS = 30.0

#: Courts : ils s'affichent sur une ligne dans le menu GNOME et le panneau.
_UNCOVERED = {
    LID: "Capot non géré (refusé par logind).",
    IDLE: "L'écran peut s'éteindre quand même.",
    SUSPEND: "Veille automatique non bloquée.",
}


def _int_param(params: dict[str, Any], key: str) -> int | None:
    value = params.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ActionError(f"Paramètre « {key} » : entier positif attendu")
    return value


class KeepAwakeModule(Module):
    """Garde la machine éveillée. L'état n'est pas conservé entre deux démarrages."""

    # Remplaçables dans les tests.
    inhibitor_factory: Any = DBusInhibitor
    battery_factory: Any = UPowerWatcher

    async def start(self) -> None:
        self._inhibitor: Inhibitor = self.inhibitor_factory(self.ctx.log)
        self._battery: BatteryWatcher = self.battery_factory(self._check_battery, self.ctx.log)
        self._leases: list[Lease] = []
        self._lock = asyncio.Lock()
        self._timer: asyncio.TimerHandle | None = None
        self._tasks: set[asyncio.Task[Any]] = set()
        self._started = 0.0
        self._until = 0.0
        self._seconds = 0
        if self.ctx.setting("activate_on_start"):
            try:
                await self._activate(None)
            except ActionError as exc:
                self.ctx.log.warning("Activation au démarrage impossible : %s", exc)

    async def stop(self) -> None:
        await self._deactivate("stopped", emit=False)
        for task in list(self._tasks):
            task.cancel()

    # -- actions ------------------------------------------------------------------------

    @action()
    def status(self, _params: dict[str, Any]) -> dict[str, Any]:
        return self._status()

    @action("start")
    async def start_action(self, params: dict[str, Any]) -> dict[str, Any]:
        """``minutes`` (0 = jusqu'à nouvel ordre) ou ``seconds`` ; sinon la durée par défaut."""
        seconds = _int_param(params, "seconds")
        if seconds is None:
            minutes = _int_param(params, "minutes")
            seconds = None if minutes is None else minutes * 60
        await self._activate(seconds)
        return self._status()

    @action("stop")
    async def stop_action(self, _params: dict[str, Any]) -> dict[str, Any]:
        await self._deactivate("user")
        return self._status()

    @action()
    async def toggle(self, params: dict[str, Any]) -> dict[str, Any]:
        if self._leases:
            return await self.stop_action(params)
        return await self.start_action(params)

    # -- réglages -----------------------------------------------------------------------

    def on_setting_changed(self, key: str, value: Any) -> None:
        if key in {"keep_display_on", "prevent_lid_sleep"} and self._leases:
            self._spawn(self._reacquire())
        elif key == "battery_threshold":
            self._check_battery()

    # -- cœur ---------------------------------------------------------------------------

    def _wanted(self) -> set[str]:
        wanted = {SUSPEND}
        if self.ctx.setting("keep_display_on"):
            wanted.add(IDLE)
        if self.ctx.setting("prevent_lid_sleep"):
            wanted.add(LID)
        return wanted

    def _battery_low(self) -> bool:
        threshold = int(self.ctx.setting("battery_threshold"))
        return threshold > 0 and self._battery.on_battery and self._battery.percentage <= threshold

    async def _activate(self, seconds: int | None) -> None:
        if seconds is None:
            seconds = int(self.ctx.setting("default_duration")) * 60
        async with self._lock:
            if not self._leases:
                # La batterie n'est suivie que pendant une session.
                await self._battery.start()
                if self._battery_low():
                    await self._battery.stop()
                    raise ActionError(f"Batterie trop faible ({self._battery.percentage:.0f} %)")
                try:
                    await self._acquire()
                except ActionError:
                    await self._battery.stop()
                    raise
            now = time.time()
            if not self._started:
                self._started = now
            self._seconds = seconds
            self._until = now + seconds if seconds else 0.0
            self._schedule()
        self._emit("user")

    async def _acquire(self) -> None:
        leases, uncovered = await self._inhibitor.acquire(self._wanted(), REASON)
        if not leases:
            raise ActionError("Aucun service de ce bureau ne permet d'empêcher la mise en veille")
        self._leases = leases
        self.ctx.set_notice(" ".join(_UNCOVERED[kind] for kind in sorted(uncovered)))

    async def _release(self) -> None:
        leases, self._leases = self._leases, []
        for lease in leases:
            try:
                await lease.release()
            except Exception as exc:  # le service a pu disparaître : l'inhibition est perdue de toute façon
                self.ctx.log.debug("Libération %s : %s", lease.backend, exc)

    async def _reacquire(self) -> None:
        async with self._lock:
            if not self._leases:
                return
            await self._release()
            try:
                await self._acquire()
            except ActionError as exc:
                self.ctx.log.warning("%s", exc)
                await self._battery.stop()
                self._reset()
                self._emit("error")
                return
        self._emit("settings")

    async def _deactivate(self, reason: str, *, emit: bool = True) -> None:
        async with self._lock:
            was_active = bool(self._leases)
            await self._release()
            await self._battery.stop()
            self._reset()
        self.ctx.set_notice("")
        if emit and was_active:
            self._emit(reason)

    def _reset(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = None
        self._started = self._until = 0.0
        self._seconds = 0

    def _schedule(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        if not self._until:
            return
        delay = max(0.0, min(TICK_SECONDS, self._until - time.time()))
        self._timer = asyncio.get_running_loop().call_later(delay, self._on_tick)

    def _on_tick(self) -> None:
        self._timer = None
        if not self._until:
            return
        if time.time() >= self._until - 0.05:
            self._spawn(self._deactivate("timer"))
        else:
            self._schedule()

    def _check_battery(self) -> None:
        if self._leases and self._battery_low():
            self._spawn(self._deactivate("battery"))

    def _spawn(self, coro: Any) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _status(self) -> dict[str, Any]:
        return {
            "active": bool(self._leases),
            "started": self._started,
            "until": self._until,
            "seconds": self._seconds,
            "display": IDLE in self._covered(),
            "lid": LID in self._covered(),
            "backends": [lease.backend for lease in self._leases],
            "battery": self._battery.percentage if self._battery.on_battery else -1.0,
        }

    def _covered(self) -> set[str]:
        return set().union(*(lease.covers for lease in self._leases)) if self._leases else set()

    def _emit(self, reason: str) -> None:
        self.ctx.emit("state-changed", {**self._status(), "reason": reason})
