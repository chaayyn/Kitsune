"""Conversions de couleurs : HEX, RGB, HSL."""

from __future__ import annotations

import colorsys
import re

RGB = tuple[int, int, int]

_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def to_hex(rgb: RGB) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def parse_hex(value: str) -> RGB:
    match = _HEX.match(value.strip())
    if not match:
        raise ValueError(f"Couleur HEX invalide : {value!r}")
    digits = match.group(1)
    return int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16)


def from_unit(red: float, green: float, blue: float) -> RGB:
    """Composantes 0–1 (portail XDG) vers 0–255."""
    return tuple(max(0, min(255, round(c * 255))) for c in (red, green, blue))  # type: ignore[return-value]


def to_rgb_text(rgb: RGB) -> str:
    return "rgb({}, {}, {})".format(*rgb)


def to_hsl_text(rgb: RGB) -> str:
    hue, light, sat = colorsys.rgb_to_hls(*(c / 255 for c in rgb))
    return f"hsl({round(hue * 360) % 360}, {round(sat * 100)}%, {round(light * 100)}%)"


def format_color(rgb: RGB, fmt: str) -> str:
    match fmt:
        case "rgb":
            return to_rgb_text(rgb)
        case "hsl":
            return to_hsl_text(rgb)
        case _:
            return to_hex(rgb)
