"""Pont entre le QML et le démon : état, modèles et commandes.

Exposé au QML sous le nom ``Saturn``. Toute la logique métier reste dans
``saturnd`` ; ici on ne fait que relayer, mettre en forme et signaler les erreurs.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, QPoint, QTimer, Signal, Slot
from PySide6.QtGui import QCursor, QGuiApplication

from saturn import paths
from saturn.ui.client import CallError, DaemonClient
from saturn.ui.models import ClipboardModel, ModuleListModel, NotesModel, SettingsModel, module_status

log = logging.getLogger(__name__)

#: Délai après lequel un démarrage du démon est considéré comme raté.
START_TIMEOUT_MS = 8000


def daemon_command() -> list[str]:
    """Commande pour lancer ``saturnd`` : l'exécutable installé, sinon le paquet courant."""
    installed = shutil.which("saturnd")
    if installed:
        return [installed]
    return [sys.executable, "-m", "saturn"]


def launch_daemon() -> Path:
    """Lance le démon détaché de l'interface. Renvoie le chemin de son journal."""
    log_path = paths.ensure_dir(paths.state_dir()) / "saturnd.log"
    env = dict(os.environ)
    package_root = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [package_root, env.get("PYTHONPATH")]))
    with open(log_path, "ab") as log_file:
        subprocess.Popen(
            daemon_command(),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=log_file,
            env=env,
            start_new_session=True,
        )
    return log_path


def coerce_setting(signature: str, value: Any) -> Any:
    """Convertit une valeur venue du QML (nombres JS en float, tableaux…) vers le type D-Bus."""
    match signature:
        case "b":
            return bool(value)
        case "x":
            number = float(value)
            if not number.is_integer():
                raise ValueError(f"{value} n'est pas un nombre entier")
            return int(number)
        case "d":
            return float(value)
        case "s":
            return str(value)
        case "as":
            if isinstance(value, str) or not isinstance(value, (list, tuple, type(None))):
                raise ValueError(f"{value!r} n'est pas une liste")
            return [str(item) for item in (value or [])]
    raise ValueError(f"Type de réglage inconnu : {signature}")


class Backend(QObject):
    connectedChanged = Signal()
    startingChanged = Signal()
    infoChanged = Signal()
    currentModuleChanged = Signal()
    panelToggleRequested = Signal()
    panelShowRequested = Signal()
    settingsRequested = Signal(str)
    clipboardRequested = Signal()
    clipboardCopied = Signal()
    clipboardStateChanged = Signal()
    scratchpadRequested = Signal()
    scratchpadStateChanged = Signal()
    noteLoaded = Signal(int, str)  # id, texte : le QML remplace le contenu de l'éditeur
    noteExported = Signal(str)
    notify = Signal(str, str)  # message, niveau ("error" ou "info")

    def __init__(self, client: DaemonClient, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.client = client
        self._modules = ModuleListModel(self)
        self._settings = SettingsModel(self)
        self._clipboard = ClipboardModel(self)
        self._clip_query = ""
        self._clip_total = 0
        self._clip_visible = False
        self._clip_was_active = False
        self._notes = NotesModel(self)
        self._current_note = -1
        self._note_font = 14
        self._saving = 0
        self._origin = f"ui-{os.getpid()}"
        self._pad_was_active = False
        self._connected = False
        self._starting = False
        self._version = ""
        self._environment: dict[str, Any] = {}
        self._current_id = ""
        self._start_timer = QTimer(self, singleShot=True, interval=START_TIMEOUT_MS)
        self._start_timer.timeout.connect(self._on_start_timeout)
        self._modules.dataChanged.connect(self._on_modules_changed)
        self._modules.modelReset.connect(self._on_modules_changed)
        self._modules.dataChanged.connect(self.clipboardStateChanged)
        self._modules.modelReset.connect(self.clipboardStateChanged)
        self._modules.rowsInserted.connect(self.clipboardStateChanged)
        for signal in (self._modules.dataChanged, self._modules.modelReset, self._modules.rowsInserted):
            signal.connect(self.scratchpadStateChanged)

        client.on_available_changed = self._on_available_changed
        client.on_module_changed = self._on_module_changed
        client.on_setting_changed = self._on_setting_changed
        client.on_module_event = self._on_module_event
        if client.available:
            self._on_available_changed(True)

    # -- propriétés ------------------------------------------------------------------

    @Property(bool, notify=connectedChanged)
    def connected(self) -> bool:
        return self._connected

    @Property(bool, notify=startingChanged)
    def starting(self) -> bool:
        return self._starting

    @Property(QObject, constant=True)
    def modules(self) -> ModuleListModel:
        return self._modules

    @Property(QObject, constant=True)
    def settings(self) -> SettingsModel:
        return self._settings

    @Property(str, notify=infoChanged)
    def version(self) -> str:
        return self._version

    @Property(str, notify=infoChanged)
    def desktop(self) -> str:
        return str(self._environment.get("desktop", ""))

    @Property(str, notify=infoChanged)
    def session(self) -> str:
        return str(self._environment.get("session", ""))

    @Property(str, notify=currentModuleChanged)
    def currentModuleId(self) -> str:
        return self._current_id

    @Property("QVariantMap", notify=currentModuleChanged)
    def currentModule(self) -> dict[str, Any]:
        return self._modules.module(self._current_id) or {}

    @Property(QObject, constant=True)
    def clipboard(self) -> ClipboardModel:
        return self._clipboard

    @Property(bool, notify=clipboardStateChanged)
    def clipboardActive(self) -> bool:
        module = self._modules.module("clipboard")
        return bool(module and module["status"] == "running")

    @Property(bool, notify=clipboardStateChanged)
    def clipboardInstalled(self) -> bool:
        return self._modules.module("clipboard") is not None

    @Property(str, notify=clipboardStateChanged)
    def clipboardNotice(self) -> str:
        module = self._modules.module("clipboard") or {}
        return str(module.get("notice") or module.get("error") or "")

    @Property(int, notify=clipboardStateChanged)
    def clipboardTotal(self) -> int:
        return self._clip_total

    @Property(QObject, constant=True)
    def notes(self) -> NotesModel:
        return self._notes

    @Property(bool, notify=scratchpadStateChanged)
    def scratchpadActive(self) -> bool:
        module = self._modules.module("scratchpad")
        return bool(module and module["status"] == "running")

    @Property(int, notify=scratchpadStateChanged)
    def currentNoteId(self) -> int:
        return self._current_note

    @Property(int, notify=scratchpadStateChanged)
    def noteFontSize(self) -> int:
        return self._note_font

    @Property(bool, notify=scratchpadStateChanged)
    def noteSaving(self) -> bool:
        return self._saving > 0

    @Property(bool, constant=True)
    def canPosition(self) -> bool:
        """Sous Wayland, seule le compositeur place les fenêtres."""
        return QGuiApplication.platformName() != "wayland"

    # -- commandes appelées par le QML -----------------------------------------------

    @Slot()
    def togglePanel(self) -> None:
        self.panelToggleRequested.emit()

    @Slot()
    def showPanel(self) -> None:
        self.panelShowRequested.emit()

    @Slot(str)
    def openSettings(self, module_id: str = "") -> None:
        target = module_id or self._current_id
        if not target and self._modules.count:
            target = self._modules.get(0)["moduleId"]
        if target:
            self.selectModule(target)
        self.settingsRequested.emit(target)

    # -- presse-papiers ----------------------------------------------------------------

    @Slot()
    def openClipboard(self) -> None:
        self.clipboardRequested.emit()
        self.searchClipboard(self._clip_query)

    @Slot(bool)
    def setClipboardVisible(self, visible: bool) -> None:
        self._clip_visible = visible

    @Slot(str)
    def searchClipboard(self, query: str) -> None:
        self._clip_query = query
        if not (self._connected and self.clipboardActive):
            self._clipboard.clear()
            return

        def done(result: dict[str, Any]) -> None:
            if query == self._clip_query:
                self._clipboard.load(result.get("items", []))
                self._clip_total = int(result.get("total", 0))
                self.clipboardStateChanged.emit()

        self.client.call_action("clipboard", "list", {"query": query, "limit": 200}, done, self._report)

    @Slot(int)
    def copyEntry(self, entry_id: int) -> None:
        self.client.call_action(
            "clipboard", "copy", {"id": entry_id}, lambda _r: self.clipboardCopied.emit(), self._report
        )

    @Slot(int, bool)
    def pinEntry(self, entry_id: int, pinned: bool) -> None:
        self.client.call_action("clipboard", "pin", {"id": entry_id, "pinned": pinned}, None, self._report)

    @Slot(int)
    def deleteEntry(self, entry_id: int) -> None:
        self.client.call_action("clipboard", "delete", {"id": entry_id}, None, self._report)

    @Slot()
    def clearClipboard(self) -> None:
        self.client.call_action("clipboard", "clear", {"keep_pinned": True}, None, self._report)

    # -- bloc-notes ------------------------------------------------------------------------

    @Slot()
    def openScratchpad(self) -> None:
        self.scratchpadRequested.emit()
        self._reload_notes(select=self._current_note)
        self.client.get_settings("scratchpad", self._apply_pad_settings, None)

    @Slot(int)
    def selectNote(self, note_id: int) -> None:
        if note_id == self._current_note:
            return
        self._current_note = note_id
        self.scratchpadStateChanged.emit()
        self._load_note(note_id)

    @Slot()
    def createNote(self) -> None:
        def created(result: dict[str, Any]) -> None:
            self._reload_notes(select=int(result["id"]))

        self.client.call_action("scratchpad", "create", {"origin": self._origin}, created, self._report)

    @Slot(int, str)
    def saveNote(self, note_id: int, body: str) -> None:
        self._saving += 1
        self.scratchpadStateChanged.emit()

        def finished(_result: Any = None) -> None:
            self._saving -= 1
            self.scratchpadStateChanged.emit()
            self._reload_notes()

        def failed(error: CallError) -> None:
            self._saving -= 1
            self.scratchpadStateChanged.emit()
            self._report(error)

        self.client.call_action(
            "scratchpad", "save", {"id": note_id, "body": body, "origin": self._origin}, finished, failed
        )

    @Slot(int)
    def deleteNote(self, note_id: int) -> None:
        ids = self._notes.ids()
        neighbour = -1
        if note_id in ids and len(ids) > 1:
            index = ids.index(note_id)
            neighbour = ids[index + 1] if index + 1 < len(ids) else ids[index - 1]

        def deleted(_result: Any) -> None:
            self._reload_notes(select=neighbour)

        self.client.call_action("scratchpad", "delete", {"id": note_id, "origin": self._origin}, deleted, self._report)

    @Slot(int)
    def exportNote(self, note_id: int) -> None:
        def exported(result: dict[str, Any]) -> None:
            self.noteExported.emit(str(result["path"]))
            self.notify.emit(f"Exportée dans {result['path']}", "info")

        self.client.call_action("scratchpad", "export", {"id": note_id}, exported, self._report)

    def _reload_notes(self, select: int = -1) -> None:
        if not (self._connected and self.scratchpadActive):
            self._notes.clear()
            return

        def listed(result: dict[str, Any]) -> None:
            self._notes.load(result.get("notes", []))
            ids = self._notes.ids()
            target = select if select in ids else (self._current_note if self._current_note in ids else -1)
            if target == -1 and ids:
                target = ids[0]
            if target != self._current_note or select != -1:
                self._current_note = target
                self.scratchpadStateChanged.emit()
                self._load_note(target)

        self.client.call_action("scratchpad", "list", {}, listed, self._report)

    def _load_note(self, note_id: int) -> None:
        if note_id < 0:
            self.noteLoaded.emit(-1, "")
            return

        def got(result: dict[str, Any]) -> None:
            if note_id == self._current_note:
                self.noteLoaded.emit(note_id, str(result["note"].get("body", "")))

        self.client.call_action("scratchpad", "get", {"id": note_id}, got, self._report)

    def _apply_pad_settings(self, values: dict[str, Any]) -> None:
        self._note_font = int(values.get("font_size", self._note_font))
        self.scratchpadStateChanged.emit()

    @Slot()
    def quit(self) -> None:
        QGuiApplication.quit()

    @Slot(int, int, result=QPoint)
    def panelPosition(self, width: int, height: int) -> QPoint:
        """Coin haut droit de l'écran sous le curseur (X11 seulement)."""
        cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(max(cursor.x() - width // 2, area.left() + 8), area.right() - width - 8)
        return QPoint(x, area.top() + 8)

    @Slot()
    def refresh(self) -> None:
        if not self._connected:
            return
        self.client.list_modules(self._modules.reset, self._report)
        self.client.get_environment(self._set_environment, self._report)
        self.client.get_version(self._set_version, self._report)

    @Slot()
    def startDaemon(self) -> None:
        if self._connected or self._starting:
            return
        try:
            log_path = launch_daemon()
        except OSError as exc:
            self.notify.emit(f"Impossible de lancer saturnd : {exc}", "error")
            return
        log.info("saturnd lancé, journal : %s", log_path)
        self._set_starting(True)
        self._start_timer.start()

    @Slot(str, bool)
    def setModuleEnabled(self, module_id: str, enabled: bool) -> None:
        self._modules.set_pending(module_id, True)

        def done(state: dict[str, Any]) -> None:
            self._modules.update(state)
            self._modules.set_pending(module_id, False)

        def failed(error: CallError) -> None:
            self._modules.set_pending(module_id, False)
            self._report(error)

        self.client.set_module_enabled(module_id, enabled, done, failed)

    @Slot(str)
    def selectModule(self, module_id: str) -> None:
        if module_id != self._current_id:
            self._current_id = module_id
            self._settings.clear()
            self.currentModuleChanged.emit()
        self._load_settings(module_id)

    @Slot(str, "QVariant")
    def setSetting(self, key: str, value: Any) -> None:
        module_id = self._current_id
        signature = self._settings.signature(key)
        if not module_id or signature is None:
            return
        try:
            converted = coerce_setting(signature, value)
        except (TypeError, ValueError) as exc:
            self._settings.refresh(key)
            self.notify.emit(str(exc), "error")
            return

        def failed(error: CallError) -> None:
            self._settings.refresh(key)
            self._report(error)

        self.client.set_setting(module_id, key, signature, converted, None, failed)

    @Slot(str)
    def resetSetting(self, key: str) -> None:
        if self._current_id:
            self.client.reset_setting(self._current_id, key, None, self._report)

    # -- évènements du client -------------------------------------------------------------

    def _on_available_changed(self, available: bool) -> None:
        self._connected = available
        self.connectedChanged.emit()
        if available:
            self._start_timer.stop()
            self._set_starting(False)
            self.refresh()
            if self._current_id:
                self._load_settings(self._current_id)
        else:
            self._modules.clear()
            self._settings.clear()

    def _on_module_changed(self, module_id: str, state: dict[str, Any]) -> None:
        self._modules.update(state)

    def _on_setting_changed(self, module_id: str, key: str, value: Any) -> None:
        if module_id == self._current_id:
            self._settings.set_value(key, value)
        if module_id == "scratchpad" and key == "font_size":
            self._note_font = int(value)
            self.scratchpadStateChanged.emit()

    def _on_module_event(self, module_id: str, event: str, data: dict[str, Any]) -> None:
        if module_id == "clipboard" and event == "history-changed" and self._clip_visible:
            self.searchClipboard(self._clip_query)
        elif module_id == "scratchpad" and event == "notes-changed" and data.get("origin") != self._origin:
            # Modifiée ailleurs (autre fenêtre, autre client) : on relit la liste et la note ouverte.
            self._reload_notes()
            if int(data.get("id", -1)) == self._current_note:
                self._load_note(self._current_note)

    def _on_modules_changed(self, *_args: Any) -> None:
        self.currentModuleChanged.emit()
        # Le module presse-papiers vient de démarrer (ou de s'arrêter) : on recharge la fenêtre.
        active = self.clipboardActive
        if active != self._clip_was_active:
            self._clip_was_active = active
            if self._clip_visible:
                self.searchClipboard(self._clip_query)
        pad = self.scratchpadActive
        if pad != self._pad_was_active:
            self._pad_was_active = pad
            self._reload_notes(select=self._current_note)

    def _on_start_timeout(self) -> None:
        if not self._connected:
            self._set_starting(False)
            log_path = paths.state_dir() / "saturnd.log"
            self.notify.emit(f"saturnd n'a pas démarré. Journal : {log_path}", "error")

    # -- interne ---------------------------------------------------------------------

    def _load_settings(self, module_id: str) -> None:
        if not self._connected or not module_id:
            return

        def got_schema(schema: list[dict[str, Any]]) -> None:
            def got_values(values: dict[str, Any]) -> None:
                if module_id == self._current_id:
                    self._settings.load(schema, values)

            self.client.get_settings(module_id, got_values, self._report)

        self.client.get_settings_schema(module_id, got_schema, self._report)

    def _set_environment(self, environment: dict[str, Any]) -> None:
        self._environment = dict(environment)
        self.infoChanged.emit()

    def _set_version(self, version: str) -> None:
        self._version = str(version)
        self.infoChanged.emit()

    def _set_starting(self, starting: bool) -> None:
        if starting != self._starting:
            self._starting = starting
            self.startingChanged.emit()

    def _report(self, error: CallError) -> None:
        self.notify.emit(error.message, "error")


__all__ = ["Backend", "coerce_setting", "daemon_command", "launch_daemon", "module_status"]
