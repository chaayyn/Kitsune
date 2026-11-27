from __future__ import annotations

import pytest

from saturn.desktop import Desktop, Family, SessionType, detect


@pytest.mark.parametrize(
    ("env", "desktop", "family", "session"),
    [
        ({"XDG_CURRENT_DESKTOP": "GNOME", "XDG_SESSION_TYPE": "wayland"}, Desktop.GNOME, Family.GNOME, SessionType.WAYLAND),
        ({"XDG_CURRENT_DESKTOP": "ubuntu:GNOME", "WAYLAND_DISPLAY": "wayland-0"}, Desktop.GNOME, Family.GNOME, SessionType.WAYLAND),
        ({"XDG_CURRENT_DESKTOP": "KDE", "XDG_SESSION_TYPE": "x11"}, Desktop.KDE, Family.KDE, SessionType.X11),
        ({"XDG_CURRENT_DESKTOP": "sway", "SWAYSOCK": "/run/sway.sock"}, Desktop.SWAY, Family.WLROOTS, SessionType.UNKNOWN),
        ({"HYPRLAND_INSTANCE_SIGNATURE": "abc", "XDG_CURRENT_DESKTOP": "Hyprland", "XDG_SESSION_TYPE": "wayland"}, Desktop.HYPRLAND, Family.WLROOTS, SessionType.WAYLAND),
        ({"XDG_CURRENT_DESKTOP": "X-Cinnamon", "DISPLAY": ":0"}, Desktop.CINNAMON, Family.OTHER, SessionType.X11),
        ({"DESKTOP_SESSION": "xfce"}, Desktop.XFCE, Family.OTHER, SessionType.UNKNOWN),
        ({"KDE_FULL_SESSION": "true"}, Desktop.KDE, Family.KDE, SessionType.UNKNOWN),
        ({}, Desktop.UNKNOWN, Family.OTHER, SessionType.UNKNOWN),
    ],
)
def test_detect(env, desktop, family, session) -> None:
    detected = detect(env)
    assert (detected.desktop, detected.family, detected.session) == (desktop, family, session)


def test_to_dict() -> None:
    detected = detect({"XDG_CURRENT_DESKTOP": "GNOME", "XDG_SESSION_TYPE": "wayland"})
    assert detected.is_wayland and not detected.is_x11
    assert detected.to_dict() == {
        "desktop": "gnome",
        "family": "gnome",
        "session": "wayland",
        "raw_desktop": "GNOME",
    }
