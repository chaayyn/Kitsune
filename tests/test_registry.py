from __future__ import annotations

import sys

import pytest

from saturn.config import Config
from saturn.errors import (
    InvalidSettingError,
    ModuleNotRunningError,
    ModuleUnavailableError,
    UnknownActionError,
    UnknownModuleError,
    UnknownSettingError,
)
from saturn.registry import Registry
from saturn.settings import Setting, SettingType


def test_discovery_reads_manifests_and_skips_invalid(fake_package: str) -> None:
    registry = Registry(fake_package)
    infos = registry.discover()
    assert sorted(infos) == ["alpha", "beta", "broken", "gamma"]
    # Lister les modules ne doit importer aucune implémentation.
    assert not [m for m in sys.modules if m.startswith(fake_package) and m.endswith(".impl")]


def test_builtin_modules_are_discovered() -> None:
    assert "clean_url" in Registry().discover()


def test_unknown_module(manager) -> None:
    with pytest.raises(UnknownModuleError):
        manager.state("nope")


def test_only_enabled_modules_are_loaded(manager, run, fake_package: str) -> None:
    run(manager.start())

    assert manager.is_running("alpha")
    assert not manager.is_running("beta")
    assert f"{fake_package}.alpha.impl" in sys.modules
    assert f"{fake_package}.beta.impl" not in sys.modules

    alpha = manager.state("alpha")
    assert alpha.enabled and alpha.running and alpha.actions == ("echo",)
    beta = manager.state("beta")
    assert not beta.enabled and not beta.running and beta.actions == ()


def test_missing_requirement_blocks_module(manager, run) -> None:
    run(manager.start())
    gamma = manager.state("gamma")
    assert gamma.enabled and not gamma.running and not gamma.available
    assert gamma.missing == ("saturn-binaire-inexistant (paquet-fictif)",)
    assert "Dépendances manquantes" in gamma.error
    with pytest.raises(ModuleUnavailableError):
        run(manager.set_enabled("gamma", True))


def test_toggle_starts_stops_and_persists(manager, run, fake_package: str) -> None:
    events = []
    manager.state_listeners.append(events.append)

    async def scenario():
        await manager.start()
        await manager.set_enabled("alpha", False)
        await manager.set_enabled("beta", True)

    run(scenario())

    impl = sys.modules[f"{fake_package}.alpha.impl"]
    assert impl.EVENTS == ["start", "stop"]
    assert not manager.is_running("alpha")
    assert manager.is_running("beta")
    assert [(s.info.id, s.enabled) for s in events] == [("alpha", False), ("beta", True)]

    reloaded = Config.load()
    assert reloaded.module_enabled("alpha") is False
    assert reloaded.module_enabled("beta") is True


def test_start_failure_is_reported_not_raised(manager, run) -> None:
    state = run(manager.set_enabled("broken", True))
    assert state.enabled and not state.running
    assert state.error == "boum"
    # Désactiver efface l'erreur.
    assert run(manager.set_enabled("broken", False)).error is None


def test_settings_defaults_validation_and_persistence(manager, run, fake_package) -> None:
    changes = []
    manager.setting_listeners.append(lambda mid, s, v: changes.append((mid, s.key, v)))
    run(manager.start())

    assert manager.settings("alpha") == {"level": 3, "mode": "fast"}
    manager.set_setting("alpha", "level", 7)
    assert manager.settings("alpha")["level"] == 7
    assert Config.load().module_settings("alpha") == {"level": 7}

    with pytest.raises(InvalidSettingError):
        manager.set_setting("alpha", "level", 42)
    with pytest.raises(InvalidSettingError):
        manager.set_setting("alpha", "mode", "medium")
    with pytest.raises(UnknownSettingError):
        manager.set_setting("alpha", "nope", 1)

    assert manager.reset_setting("alpha", "level") == 3
    assert changes == [("alpha", "level", 7), ("alpha", "level", 3)]
    impl = sys.modules[f"{fake_package}.alpha.impl"]
    assert ("setting", "level", 7) in impl.EVENTS


def test_invalid_stored_setting_falls_back_to_default(manager) -> None:
    manager.config.set_module_setting("alpha", "level", "beaucoup")
    assert manager.settings("alpha")["level"] == 3


def test_actions_and_events(manager, run) -> None:
    events = []
    manager.event_listeners.append(lambda *args: events.append(args))

    async def scenario():
        await manager.start()
        result = await manager.call_action("alpha", "echo", {"text": "salut"})
        with pytest.raises(UnknownActionError):
            await manager.call_action("alpha", "nope", {})
        with pytest.raises(ModuleNotRunningError):
            await manager.call_action("beta", "anything", {})
        return result

    assert run(scenario()) == {"echo": "salut", "level": 3}
    assert events == [("alpha", "echoed", {"text": "salut"})]


def test_stop_stops_everything(manager, run, fake_package) -> None:
    async def scenario():
        await manager.start()
        await manager.stop()

    run(scenario())
    assert not manager.is_running("alpha")
    assert sys.modules[f"{fake_package}.alpha.impl"].EVENTS == ["start", "stop"]


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        (Setting("b", SettingType.BOOL, False, "B"), 1),
        (Setting("i", SettingType.INT, 0, "I"), True),
        (Setting("i", SettingType.INT, 0, "I"), 1.5),
        (Setting("f", SettingType.FLOAT, 0.0, "F"), float("nan")),
        (Setting("s", SettingType.STRING, "", "S"), 3),
        (Setting("l", SettingType.STRING_LIST, [], "L"), ["ok", 2]),
    ],
)
def test_setting_rejects_wrong_types(setting: Setting, value) -> None:
    with pytest.raises(InvalidSettingError):
        setting.validate(value)


def test_setting_default_is_validated_and_copied() -> None:
    with pytest.raises(ValueError):
        Setting("x", SettingType.INT, 99, "X", maximum=10)
    setting = Setting("l", SettingType.STRING_LIST, ["a"], "L")
    first = setting.default_value()
    first.append("b")
    assert setting.default_value() == ["a"]
