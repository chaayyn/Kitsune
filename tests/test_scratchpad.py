from __future__ import annotations

from pathlib import Path

import pytest

from saturn.config import Config
from saturn.errors import ActionError
from saturn.manager import ModuleManager
from saturn.modules.scratchpad.store import NotesStore, note_preview, note_title, safe_filename
from saturn.registry import Registry
from saturn.storage import Database


@pytest.mark.parametrize(
    ("body", "title"),
    [
        ("# Courses\n- pain", "Courses"),
        ("\n\n   Idée du jour  \nsuite", "Idée du jour"),
        ("### ", "Sans titre"),
        ("", "Sans titre"),
        ("x" * 100, "x" * 60),
    ],
)
def test_note_title(body: str, title: str) -> None:
    assert note_title(body) == title


def test_preview_and_filenames() -> None:
    assert note_preview("# Titre\n\nligne 1\nligne 2") == "ligne 1 ligne 2"
    assert safe_filename("Réunion : jeudi / 14h ?") == "Réunion-jeudi-14h"
    assert safe_filename("../../etc/passwd") == "etcpasswd"
    assert safe_filename("***") == "note"


def test_store_order_save_and_move(tmp_path: Path) -> None:
    store = NotesStore(Database(tmp_path / "notes.db").connection)
    a, b, c = (store.create(f"# {name}") for name in "ABC")
    assert [n["title"] for n in store.list()] == ["A", "B", "C"]

    assert store.save(a, "# A modifiée\nmots en plus", now=10) is True
    assert store.save(a, "# A modifiée\nmots en plus", now=20) is False  # rien n'a changé
    note = store.get(a)
    assert note["updated"] == 10 and note["words"] == 6 and note["body"].startswith("# A")

    store.move(c, 0)
    assert [n["id"] for n in store.list()] == [c, a, b]
    store.move(c, 99)
    assert [n["id"] for n in store.list()] == [a, b, c]
    assert store.delete(b) and not store.delete(b)


@pytest.fixture
def pad(env) -> ModuleManager:
    manager = ModuleManager(Registry(), Config.load(), env)
    manager.discover()
    return manager


def test_module_actions(pad: ModuleManager, run, isolated_xdg: Path) -> None:
    events = []
    pad.event_listeners.append(lambda mid, event, data: events.append((mid, event, data)))

    async def scenario():
        await pad.start()
        assert pad.is_running("scratchpad")  # actif par défaut
        call = pad.call_action
        notes = (await call("scratchpad", "list", {}))["notes"]
        assert [n["title"] for n in notes] == ["Bienvenue dans le bloc-notes"]

        new = (await call("scratchpad", "create", {"origin": "ui-1"}))["id"]
        saved = await call("scratchpad", "save", {"id": new, "body": "# Plan\nÉtape 1", "origin": "ui-1"})
        assert saved == {"saved": True, "title": "Plan"}
        assert (await call("scratchpad", "get", {"id": new}))["note"]["body"] == "# Plan\nÉtape 1"

        # Export : jamais d'écrasement, dossier configurable.
        pad.set_setting("scratchpad", "export_dir", str(isolated_xdg / "exports"))
        first = Path((await call("scratchpad", "export", {"id": new}))["path"])
        second = Path((await call("scratchpad", "export", {"id": new}))["path"])
        assert first.name == "Plan.md" and second.name == "Plan-2.md"
        assert first.read_text() == "# Plan\nÉtape 1"
        pad.set_setting("scratchpad", "export_dir", "relatif/sans/racine")
        with pytest.raises(ActionError):
            await call("scratchpad", "export", {"id": new})

        # Supprimer la dernière note en recrée une vide : il reste toujours un onglet.
        for note in (await call("scratchpad", "list", {}))["notes"]:
            await call("scratchpad", "delete", {"id": note["id"]})
        remaining = (await call("scratchpad", "list", {}))["notes"]
        assert [n["title"] for n in remaining] == ["Sans titre"]

        with pytest.raises(ActionError):
            await call("scratchpad", "save", {"id": 999, "body": "x"})
        with pytest.raises(ActionError):
            await call("scratchpad", "save", {"id": remaining[0]["id"]})
        await pad.stop()

    run(scenario())
    changes = [data for mid, event, data in events if event == "notes-changed"]
    assert changes[0] == {"id": changes[0]["id"], "origin": "ui-1"}
