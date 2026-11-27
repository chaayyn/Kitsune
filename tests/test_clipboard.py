from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

from saturn.config import Config
from saturn.desktop import Desktop, Environment, Family, SessionType
from saturn.errors import ActionError, ModuleUnavailableError
from saturn.manager import ModuleManager
from saturn.modules.clipboard import backends
from saturn.modules.clipboard.content import ClipContent, choose_mime, from_bytes, parse_uri_list, to_uri_list
from saturn.modules.clipboard.secrets import secret_reason
from saturn.modules.clipboard.store import ClipboardStore
from saturn.registry import Registry
from saturn.storage import Database

# -- contenu ---------------------------------------------------------------------------


def test_choose_mime_prefers_files_then_images_then_text() -> None:
    offered = ["text/plain", "image/png", "text/uri-list", "TARGETS"]
    assert choose_mime(offered) == "text/uri-list"
    assert choose_mime(offered, store_files=False) == "image/png"
    assert choose_mime(offered, store_images=False, store_files=False) == "text/plain"
    assert choose_mime(["UTF8_STRING", "STRING"]) == "UTF8_STRING"
    assert choose_mime(["application/x-whatever"]) is None


def test_uri_lists_roundtrip() -> None:
    data = "# commentaire\r\nfile:///home/a/caf%C3%A9.txt\r\nhttps://exemple.fr/\r\nfile:///tmp/b\r\n"
    assert parse_uri_list(data) == ("/home/a/café.txt", "/tmp/b")
    assert parse_uri_list(to_uri_list(["/home/a/café.txt"])) == ("/home/a/café.txt",)


def test_from_bytes_rejects_empty_and_builds_previews() -> None:
    assert from_bytes("text/plain", b"   \n") is None
    text = from_bytes("text/plain", "  Bonjour\n  le monde ".encode())
    assert text.kind == "text" and text.preview == "Bonjour le monde"
    image = from_bytes("image/png", b"\x89PNG...")
    assert image.kind == "image" and image.preview == "Image PNG"
    files = from_bytes("text/uri-list", b"file:///tmp/a.txt\r\nfile:///tmp/dossier/\r\n")
    assert files.files == ("/tmp/a.txt", "/tmp/dossier/") and files.preview == "a.txt, dossier"
    assert ClipContent("text", text="a").digest != ClipContent("text", text="b").digest


# -- secrets ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "mimes", "reason"),
    [
        ("mot de passe", ["text/plain", "x-kde-passwordManagerHint"], "gestionnaire de mots de passe"),
        ("-----BEGIN OPENSSH PRIVATE KEY-----\nabc", [], "clé privée"),
        ("-----BEGIN RSA PRIVATE KEY-----", [], "clé privée"),
        ("AKIAIOSFODNN7EXAMPLE", [], "clé AWS"),
        ("ghp_" + "a" * 36, [], "jeton GitHub"),
        ("sk-ant-api03-" + "x" * 30, [], "clé d'API"),
        ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U", [], "JWT"),
    ],
)
def test_secrets_are_detected(text, mimes, reason) -> None:
    assert secret_reason(text, mimes) == reason


@pytest.mark.parametrize(
    "text", ["Bonjour", "https://github.com/chaayyn/Kitsune", "sk-court", "-----BEGIN PUBLIC KEY-----"]
)
def test_ordinary_text_is_not_a_secret(text) -> None:
    assert secret_reason(text, ["text/plain"]) is None


# -- stockage ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> ClipboardStore:
    return ClipboardStore(Database(tmp_path / "clip.db").connection, tmp_path / "images")


def test_store_dedupes_orders_and_searches(store: ClipboardStore) -> None:
    first = store.add(ClipContent("text", text="Bonjour le monde"), now=1)
    store.add(ClipContent("text", text="Autre chose"), now=2)
    again = store.add(ClipContent("text", text="Bonjour le monde"), now=3)

    assert again.id == first.id and not again.new
    items, total = store.search()
    assert total == 2 and [item["preview"] for item in items] == ["Bonjour le monde", "Autre chose"]
    items, total = store.search("MONDE")
    assert total == 1 and items[0]["id"] == first.id


def test_store_pins_survive_pruning_and_clear(store: ClipboardStore) -> None:
    ids = [store.add(ClipContent("text", text=f"n°{i}"), now=i).id for i in range(10)]
    store.set_pinned(ids[0], True)

    assert store.prune(max_items=3, max_age_days=0, now=100) == 6
    items, _ = store.search()
    assert [item["preview"] for item in items] == ["n°0", "n°9", "n°8", "n°7"]
    assert items[0]["pinned"] is True

    assert store.prune(max_items=100, max_age_days=1, now=10 + 2 * 86400) == 3
    assert store.clear() == 0
    assert store.count() == 1
    assert store.clear(keep_pinned=False) == 1


def test_store_keeps_images_on_disk(store: ClipboardStore) -> None:
    added = store.add(ClipContent("image", image=b"\x89PNG-data", mime="image/png"))
    entry = store.get(added.id)
    image = Path(entry["image"])
    assert image.read_bytes() == b"\x89PNG-data" and oct(image.stat().st_mode)[-3:] == "600"
    assert store.content(added.id).image == b"\x89PNG-data"
    store.delete(added.id)
    assert not image.exists()


# -- module, avec un faux accès au presse-papiers -----------------------------------------


class FakeBackend(backends.ClipboardBackend):
    name = "fake"
    instances: list[FakeBackend] = []

    def __init__(self, ctx, on_content) -> None:
        super().__init__(ctx, on_content)
        self.written: list[ClipContent] = []
        self.cleared = 0
        FakeBackend.instances.append(self)

    async def write(self, content: ClipContent) -> None:
        self.written.append(content)

    async def clear(self) -> None:
        self.cleared += 1


@pytest.fixture
def clip_manager(monkeypatch, env: Environment) -> ModuleManager:
    FakeBackend.instances.clear()
    monkeypatch.setattr(backends, "make_backend", FakeBackend)
    manager = ModuleManager(Registry(), Config.load(), env)
    manager.discover()
    return manager


async def settle() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


def test_module_records_filters_and_copies(clip_manager: ModuleManager, run) -> None:
    events = []
    clip_manager.event_listeners.append(lambda mid, event, data: events.append((mid, event)))

    async def scenario():
        await clip_manager.start()
        assert not clip_manager.is_running("clipboard")  # désactivé par défaut
        await clip_manager.set_enabled("clipboard", True)

        call = clip_manager.call_action
        assert (await call("clipboard", "push", {"text": "Bonjour"}))["accepted"]
        await call("clipboard", "push", {"text": "ghp_" + "b" * 36})
        await call("clipboard", "push", {"text": "secret", "mimes": ["x-kde-passwordManagerHint"]})
        await call("clipboard", "push", {"uris": "file:///tmp/rapport.pdf\r\n"})
        await call("clipboard", "push", {"image": b"\x89PNG", "mime": "image/png"})
        await settle()

        listing = await call("clipboard", "list", {})
        assert [item["kind"] for item in listing["items"]] == ["image", "files", "text"]
        assert listing["total"] == 3

        text_id = listing["items"][2]["id"]
        await call("clipboard", "copy", {"id": text_id})
        backend = FakeBackend.instances[-1]
        assert backend.written == [ClipContent("text", text="Bonjour", mime="text/plain")]
        assert (await call("clipboard", "list", {}))["items"][0]["id"] == text_id  # remonté

        await call("clipboard", "pin", {"id": text_id, "pinned": True})
        assert (await call("clipboard", "get", {"id": text_id}))["entry"]["pinned"] is True
        assert (await call("clipboard", "clear", {}))["removed"] == 2
        assert (await call("clipboard", "list", {"query": "bonj"}))["total"] == 1

        with pytest.raises(ActionError):
            await call("clipboard", "copy", {"id": 9999})
        with pytest.raises(ActionError):
            await call("clipboard", "push", {})
        await clip_manager.stop()

    run(scenario())
    assert ("clipboard", "ignored") in events
    assert events.count(("clipboard", "history-changed")) >= 4


def test_settings_disable_images_and_clean_links(clip_manager: ModuleManager, run) -> None:
    async def scenario():
        await clip_manager.start()  # Clean URL est actif par défaut
        await clip_manager.set_enabled("clipboard", True)
        clip_manager.set_setting("clipboard", "store_images", False)
        clip_manager.set_setting("clipboard", "clean_links", True)
        call = clip_manager.call_action

        await call("clipboard", "push", {"image": b"\x89PNG", "mime": "image/png"})
        await call("clipboard", "push", {"text": "https://exemple.fr/?id=1&utm_source=x"})
        await settle()

        items = (await call("clipboard", "list", {}))["items"]
        assert [item["text"] for item in items] == ["https://exemple.fr/?id=1"]
        assert FakeBackend.instances[-1].written[-1].text == "https://exemple.fr/?id=1"
        await clip_manager.stop()

    run(scenario())


def test_clear_after_delay(clip_manager: ModuleManager, run) -> None:
    async def scenario():
        await clip_manager.start()
        clip_manager.set_setting("clipboard", "clear_after", 1)
        await clip_manager.set_enabled("clipboard", True)
        await clip_manager.call_action("clipboard", "push", {"text": "éphémère"})
        await asyncio.sleep(1.3)
        cleared = FakeBackend.instances[-1].cleared
        await clip_manager.stop()
        return cleared

    assert run(scenario()) == 1


def test_wl_clipboard_is_only_required_outside_gnome(isolated_xdg, monkeypatch) -> None:
    monkeypatch.setenv("PATH", "/nonexistent")
    registry = Registry()
    registry.discover()
    info = registry.info("clipboard")
    gnome = Environment(Desktop.GNOME, Family.GNOME, SessionType.WAYLAND)
    kde = Environment(Desktop.KDE, Family.KDE, SessionType.WAYLAND)
    x11 = Environment(Desktop.KDE, Family.KDE, SessionType.X11)
    assert info.missing_requirements(gnome) == []
    assert info.missing_requirements(x11) == []
    assert {req.name for req in info.missing_requirements(kde)} == {"wl-paste", "wl-copy"}

    manager = ModuleManager(registry, Config.load(), kde)
    with pytest.raises(ModuleUnavailableError):
        asyncio.run(manager.set_enabled("clipboard", True))


def test_notice_is_reported_in_module_state(clip_manager: ModuleManager, run) -> None:
    states = []
    clip_manager.state_listeners.append(states.append)

    async def scenario():
        await clip_manager.start()
        await clip_manager.set_enabled("clipboard", True)
        FakeBackend.instances[-1].ctx.set_notice("Extension absente")
        notice = clip_manager.state("clipboard").notice
        FakeBackend.instances[-1].ctx.set_notice("")
        await clip_manager.stop()
        return notice

    assert run(scenario()) == "Extension absente"
    assert [s.notice for s in states if s.info.id == "clipboard"][-2:] == ["Extension absente", ""]


# -- wl-clipboard (faux programmes qui imitent wl-paste / wl-copy) ---------------------------

FAKE_WL_PASTE = """\
#!/bin/sh
S="$FAKE_WL_STATE"
case "$1" in
  --watch)
    shift; last=""
    while true; do
      cur=$(cat "$S/serial" 2>/dev/null)
      if [ "$cur" != "$last" ]; then last="$cur"; "$@"; fi
      sleep 0.05
    done ;;
  --list-types) cat "$S/types" 2>/dev/null ;;
  --no-newline) cat "$S/data/$(printf %s "$3" | tr '/;=' '___')" ;;
esac
"""

FAKE_WL_COPY = """\
#!/bin/sh
S="$FAKE_WL_STATE"
if [ "$1" = "--clear" ]; then : > "$S/types"; else
  name=$(printf %s "$2" | tr '/;=' '___')
  cat > "$S/data/$name"; printf '%s\\n' "$2" > "$S/types"
fi
date +%s%N > "$S/serial"
"""


@pytest.fixture
def fake_wl(tmp_path: Path, monkeypatch) -> Path:
    bin_dir = tmp_path / "bin"
    state = tmp_path / "wl-state"
    (state / "data").mkdir(parents=True)
    bin_dir.mkdir()
    for name, script in (("wl-paste", FAKE_WL_PASTE), ("wl-copy", FAKE_WL_COPY)):
        (bin_dir / name).write_text(script)
        (bin_dir / name).chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_WL_STATE", str(state))
    return state


def _wl_copy(text: str, mime: str = "text/plain;charset=utf-8") -> None:
    subprocess.run(["wl-copy", "--type", mime], input=text.encode(), check=True)


def test_wl_clipboard_backend(fake_wl: Path, run) -> None:
    kde = Environment(Desktop.KDE, Family.KDE, SessionType.WAYLAND)
    manager = ModuleManager(Registry(), Config.load(), kde)
    manager.discover()

    async def wait_for(predicate, timeout=5.0):
        end = time.monotonic() + timeout
        while not predicate():
            assert time.monotonic() < end, "délai dépassé"
            await asyncio.sleep(0.05)

    async def listing():
        return (await manager.call_action("clipboard", "list", {}))["items"]

    async def scenario():
        await manager.set_enabled("clipboard", True)
        _wl_copy("Copié dans KDE")
        await asyncio.sleep(0.4)
        items = await listing()
        assert [item["text"] for item in items] == ["Copié dans KDE"]

        _wl_copy("file:///tmp/photo.jpg\r\n", "text/uri-list")
        await asyncio.sleep(0.4)
        assert (await listing())[0]["files"] == ["/tmp/photo.jpg"]

        # Recopier depuis l'historique passe par wl-copy.
        await manager.call_action("clipboard", "copy", {"id": items[0]["id"]})
        assert (fake_wl / "types").read_text().strip() == "text/plain;charset=utf-8"
        await manager.set_enabled("clipboard", False)

    run(scenario())


# -- X11 (Xvfb + xclip) ------------------------------------------------------------------------


@pytest.mark.skipif(
    not (shutil.which("Xvfb") and shutil.which("xclip")), reason="Xvfb ou xclip absent"
)
def test_x11_backend(tmp_path: Path) -> None:
    """Le module X11 tourne dans un processus à part, avec son propre affichage Xvfb."""
    script = tmp_path / "x11_check.py"
    script.write_text(textwrap.dedent("""
        import asyncio, subprocess, sys
        from gi.events import GLibEventLoop
        from gi.repository import GLib
        from saturn.config import Config
        from saturn.desktop import Desktop, Environment, Family, SessionType
        from saturn.manager import ModuleManager
        from saturn.registry import Registry

        async def main():
            env = Environment(Desktop.XFCE, Family.OTHER, SessionType.X11)
            manager = ModuleManager(Registry(), Config.load(), env)
            manager.discover()
            await manager.set_enabled("clipboard", True)
            assert manager.is_running("clipboard"), manager.state("clipboard").error
            await asyncio.sleep(0.2)
            # xclip reste en arrière-plan pour servir la sélection : aucun tube vers lui.
            subprocess.run(["xclip", "-selection", "clipboard", "-i"], input=b"Depuis X11", check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for _ in range(60):
                await asyncio.sleep(0.1)
                items = (await manager.call_action("clipboard", "list", {}))["items"]
                if items:
                    break
            assert [i["text"] for i in items] == ["Depuis X11"], items
            await manager.call_action("clipboard", "push", {"text": "Écrit par Saturn"})
            await asyncio.sleep(0.3)
            entry = (await manager.call_action("clipboard", "list", {"query": "Saturn"}))["items"][0]
            await manager.call_action("clipboard", "copy", {"id": entry["id"]})
            await asyncio.sleep(0.3)
            out = await asyncio.to_thread(subprocess.run, ["xclip", "-selection", "clipboard", "-o"],
                                          capture_output=True, timeout=5)
            assert out.stdout.decode() == "Écrit par Saturn", out
            await manager.stop()
            print("ok")

        asyncio.run(main(), loop_factory=lambda: GLibEventLoop(GLib.MainContext.default()))
    """))
    display = ":%d" % (90 + os.getpid() % 50)
    xvfb = subprocess.Popen(["Xvfb", display, "-nolisten", "tcp"], stderr=subprocess.DEVNULL)
    try:
        time.sleep(0.8)
        env = dict(os.environ, DISPLAY=display, GDK_BACKEND="x11",
                   PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        env.pop("WAYLAND_DISPLAY", None)
        log = tmp_path / "x11.log"
        with log.open("w") as out:
            code = subprocess.run(["python3", str(script)], env=env, stdout=out, stderr=out, timeout=60).returncode
        output = log.read_text()
        assert code == 0 and output.strip().endswith("ok"), output[-3000:]
    finally:
        xvfb.terminate()
        xvfb.wait()
