from __future__ import annotations

import json
import stat
from pathlib import Path

from saturn import paths
from saturn.config import Config


def test_paths_follow_xdg(isolated_xdg: Path) -> None:
    assert paths.config_dir() == isolated_xdg / "config" / "saturn"
    assert paths.data_dir() == isolated_xdg / "data" / "saturn"


def test_relative_xdg_values_are_ignored(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", "relatif/config")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert paths.config_dir() == tmp_path / ".config" / "saturn"


def test_missing_file_gives_empty_config(isolated_xdg: Path) -> None:
    config = Config.load()
    assert config.path == isolated_xdg / "config" / "saturn" / "config.json"
    assert config.module_enabled("anything") is None
    assert config.module_settings("anything") == {}
    assert not config.path.exists()


def test_roundtrip_and_permissions() -> None:
    config = Config.load()
    config.set_module_enabled("clean_url", False)
    config.set_module_setting("clean_url", "extra_params", ["ref_*"])
    config.save()

    reloaded = Config.load()
    assert reloaded.module_enabled("clean_url") is False
    assert reloaded.module_settings("clean_url") == {"extra_params": ["ref_*"]}
    assert stat.S_IMODE(config.path.stat().st_mode) == 0o600
    assert json.loads(config.path.read_text())["version"] == 1
    # Aucun fichier temporaire ne traîne après l'écriture atomique.
    assert [p.name for p in config.path.parent.iterdir()] == ["config.json"]


def test_reset_setting() -> None:
    config = Config.load()
    config.set_module_setting("m", "k", 1)
    assert config.reset_module_setting("m", "k") is True
    assert config.reset_module_setting("m", "k") is False
    assert config.module_settings("m") == {}


def test_corrupted_file_is_set_aside() -> None:
    path = paths.ensure_dir(paths.config_dir()) / "config.json"
    path.write_text("{ pas du json")

    config = Config.load()

    assert config.module_enabled("x") is None
    backups = list(path.parent.glob("config.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_text() == "{ pas du json"


def test_unexpected_shapes_are_sanitized() -> None:
    path = paths.ensure_dir(paths.config_dir()) / "config.json"
    path.write_text(
        json.dumps(
            {"modules": {"a": {"enabled": "oui", "settings": {"k": 1}}, "b": [1, 2], "c": {}}}
        )
    )
    config = Config.load()
    assert config.module_enabled("a") is None
    assert config.module_settings("a") == {"k": 1}
    assert config.module_settings("b") == {}
