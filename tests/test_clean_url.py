from __future__ import annotations

import pytest

from saturn.config import Config
from saturn.errors import ActionError
from saturn.manager import ModuleManager
from saturn.modules.clean_url.cleaner import clean_url, looks_like_url
from saturn.registry import Registry


@pytest.mark.parametrize(
    ("url", "expected", "removed"),
    [
        (
            "https://example.com/page?utm_source=x&utm_medium=y&id=42",
            "https://example.com/page?id=42",
            ("utm_source", "utm_medium"),
        ),
        (
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&si=abc123",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            ("si",),
        ),
        ("https://shop.example/?fbclid=AbC#avis", "https://shop.example/#avis", ("fbclid",)),
        ("https://a.example/?GCLID=1&UTM_Campaign=z", "https://a.example/", ("GCLID", "UTM_Campaign")),
        # Les paramètres conservés gardent leur encodage d'origine.
        (
            "https://a.example/s?q=caf%C3%A9+cr%C3%A8me&utm_term=x&tag=a%2Fb",
            "https://a.example/s?q=caf%C3%A9+cr%C3%A8me&tag=a%2Fb",
            ("utm_term",),
        ),
    ],
)
def test_tracking_parameters_are_removed(url: str, expected: str, removed: tuple[str, ...]) -> None:
    result = clean_url(url)
    assert result.url == expected
    assert result.removed == removed
    assert result.changed


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/page?id=42&lang=fr",
        "https://example.com/",
        "ftp://example.com/?utm_source=x",
        "pas une url",
        "voir https://example.com/?utm_source=x pour plus",
        "",
    ],
)
def test_untouched_inputs_are_returned_as_is(url: str) -> None:
    result = clean_url(url)
    assert result.url == url
    assert not result.changed


def test_extra_and_keep_patterns() -> None:
    url = "https://a.example/?ref_id=1&utm_source=x&keep=1"
    result = clean_url(url, extra=["ref_*"], keep=["utm_source"])
    assert result.url == "https://a.example/?utm_source=x&keep=1"
    assert result.removed == ("ref_id",)


def test_looks_like_url() -> None:
    assert looks_like_url("  https://example.com/a  ")
    assert not looks_like_url("example.com")
    assert not looks_like_url("https://")


def test_clean_action_through_the_manager(env, run) -> None:
    manager = ModuleManager(Registry(), Config.load(), env)
    manager.discover()

    async def scenario():
        await manager.start()
        assert manager.is_running("clean_url")
        manager.set_setting("clean_url", "extra_params", ["ref"])
        result = await manager.call_action(
            "clean_url", "clean", {"url": "https://x.example/?ref=a&utm_source=b&p=1"}
        )
        with pytest.raises(ActionError):
            await manager.call_action("clean_url", "clean", {})
        await manager.stop()
        return result

    assert run(scenario()) == {
        "url": "https://x.example/?p=1",
        "changed": True,
        "removed": ["ref", "utm_source"],
    }
