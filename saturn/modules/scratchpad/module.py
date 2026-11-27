from __future__ import annotations

from pathlib import Path
from typing import Any

from saturn import paths
from saturn.errors import ActionError
from saturn.module import Module, action
from saturn.modules.scratchpad.store import NotesStore, note_title, safe_filename

WELCOME = """# Bienvenue dans le bloc-notes

Tout ce que vous tapez est enregistré au fil de la frappe, sur cet ordinateur.

- Une note par onglet, `+` pour en ouvrir une autre
- **Aperçu** affiche le Markdown mis en forme
- **Exporter** écrit la note en `.md`
"""


def _note_id(params: dict[str, Any]) -> int:
    value = params.get("id")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ActionError("Paramètre « id » (entier) requis")
    return value


class ScratchpadModule(Module):
    """Notes rapides. L'interface enregistre au fil de la frappe (action ``save``)."""

    async def start(self) -> None:
        self.store = NotesStore(self.ctx.database().connection)
        if self.store.count() == 0:
            self.store.create(WELCOME)

    def _changed(self, note_id: int | None = None, origin: str = "") -> None:
        # « origin » permet à la fenêtre qui a enregistré d'ignorer son propre écho.
        self.ctx.emit("notes-changed", {"id": note_id if note_id is not None else -1, "origin": origin})

    @action("list")
    def list_notes(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {"notes": self.store.list()}

    @action()
    def get(self, params: dict[str, Any]) -> dict[str, Any]:
        note = self.store.get(_note_id(params))
        if note is None:
            raise ActionError("Note introuvable")
        return {"note": note}

    @action()
    def create(self, params: dict[str, Any]) -> dict[str, Any]:
        note_id = self.store.create(str(params.get("body", "")))
        self._changed(note_id, str(params.get("origin", "")))
        return {"id": note_id}

    @action()
    def save(self, params: dict[str, Any]) -> dict[str, Any]:
        note_id = _note_id(params)
        body = params.get("body")
        if not isinstance(body, str):
            raise ActionError("Paramètre « body » (texte) requis")
        if self.store.get(note_id) is None:
            raise ActionError("Note introuvable")
        try:
            changed = self.store.save(note_id, body)
        except ValueError as exc:
            raise ActionError(str(exc)) from exc
        if changed:
            self._changed(note_id, str(params.get("origin", "")))
        return {"saved": changed, "title": note_title(body)}

    @action()
    def delete(self, params: dict[str, Any]) -> dict[str, Any]:
        note_id = _note_id(params)
        deleted = self.store.delete(note_id)
        if deleted and self.store.count() == 0:
            self.store.create("")  # toujours au moins un onglet
        if deleted:
            self._changed(None, str(params.get("origin", "")))
        return {"deleted": deleted}

    @action()
    def move(self, params: dict[str, Any]) -> dict[str, Any]:
        self.store.move(_note_id(params), int(params.get("position", 0)))
        self._changed(None, str(params.get("origin", "")))
        return {}

    @action()
    def export(self, params: dict[str, Any]) -> dict[str, Any]:
        """Écrit la note en Markdown dans le dossier d'export (sans jamais écraser un fichier)."""
        note = self.store.get(_note_id(params))
        if note is None:
            raise ActionError("Note introuvable")
        directory = Path(self.ctx.setting("export_dir")).expanduser()
        if not directory.is_absolute():
            raise ActionError("Le dossier d'export doit être un chemin absolu (ou commencer par ~)")
        paths.ensure_dir(directory)
        base = safe_filename(note["title"])
        target = directory / f"{base}.md"
        counter = 2
        while target.exists():
            target = directory / f"{base}-{counter}.md"
            counter += 1
        target.write_text(note["body"], encoding="utf-8")
        return {"path": str(target)}
