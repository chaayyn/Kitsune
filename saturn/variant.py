"""Conversion de valeurs Python en ``GLib.Variant`` (partagée par le démon et l'interface)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from gi.repository import GLib

_INT64 = range(-(2**63), 2**63)


def to_variant(value: Any) -> GLib.Variant:
    """Convertit une valeur Python en ``GLib.Variant`` en devinant son type."""
    if isinstance(value, GLib.Variant):
        return value
    if isinstance(value, bool):
        return GLib.Variant("b", value)
    if isinstance(value, int):
        if value not in _INT64:
            raise TypeError(f"Entier hors limites pour D-Bus : {value}")
        return GLib.Variant("x", value)
    if isinstance(value, float):
        return GLib.Variant("d", value)
    if isinstance(value, str):
        return GLib.Variant("s", value)
    if isinstance(value, (bytes, bytearray)):
        return GLib.Variant("ay", bytes(value))
    if isinstance(value, Mapping):
        return GLib.Variant("a{sv}", vardict(value))
    if isinstance(value, (list, tuple)):
        if all(isinstance(item, str) for item in value):
            return GLib.Variant("as", list(value))
        if all(isinstance(item, Mapping) for item in value):
            return GLib.Variant("aa{sv}", [vardict(item) for item in value])
        return GLib.Variant("av", [to_variant(item) for item in value])
    raise TypeError(f"Type non transmissible par D-Bus : {type(value).__name__}")


def vardict(mapping: Mapping[str, Any]) -> dict[str, GLib.Variant]:
    """Prépare un dictionnaire pour une signature ``a{sv}`` (les ``None`` sont omis)."""
    return {str(key): to_variant(value) for key, value in mapping.items() if value is not None}
