"""Description typée des réglages d'un module, avec validation."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from saturn.errors import InvalidSettingError


class SettingType(StrEnum):
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    CHOICE = "choice"
    STRING_LIST = "string_list"


#: Signature D-Bus de chaque type, utilisée pour sérialiser les valeurs.
DBUS_SIGNATURES: dict[SettingType, str] = {
    SettingType.BOOL: "b",
    SettingType.INT: "x",
    SettingType.FLOAT: "d",
    SettingType.STRING: "s",
    SettingType.CHOICE: "s",
    SettingType.STRING_LIST: "as",
}


@dataclass(frozen=True)
class Setting:
    """Un réglage exposé par un module.

    ``default`` est validé à la création : un manifeste incohérent échoue
    immédiatement plutôt qu'au premier accès.
    """

    key: str
    type: SettingType
    default: Any
    label: str
    description: str = ""
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    _normalized_default: Any = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.key.isidentifier():
            raise ValueError(f"Clé de réglage invalide : {self.key!r}")
        if self.type is SettingType.CHOICE and not self.choices:
            raise ValueError(f"Le réglage {self.key!r} de type choice n'a aucun choix")
        try:
            normalized = self.validate(self.default)
        except InvalidSettingError as exc:
            raise ValueError(f"Valeur par défaut invalide pour {self.key!r} : {exc}") from exc
        object.__setattr__(self, "_normalized_default", normalized)

    @property
    def dbus_signature(self) -> str:
        return DBUS_SIGNATURES[self.type]

    def default_value(self) -> Any:
        """Copie de la valeur par défaut (les listes ne sont jamais partagées)."""
        value = self._normalized_default
        return list(value) if isinstance(value, list) else value

    def validate(self, value: Any) -> Any:
        """Retourne ``value`` normalisée, ou lève :class:`InvalidSettingError`."""
        match self.type:
            case SettingType.BOOL:
                if not isinstance(value, bool):
                    raise self._error(value, "un booléen")
                return value
            case SettingType.INT:
                if isinstance(value, bool) or not isinstance(value, int):
                    raise self._error(value, "un entier")
                self._check_range(value)
                return value
            case SettingType.FLOAT:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise self._error(value, "un nombre")
                value = float(value)
                if not math.isfinite(value):
                    raise self._error(value, "un nombre fini")
                self._check_range(value)
                return value
            case SettingType.STRING:
                if not isinstance(value, str):
                    raise self._error(value, "du texte")
                return value
            case SettingType.CHOICE:
                if value not in self.choices:
                    raise self._error(value, "l'une des valeurs " + ", ".join(self.choices))
                return value
            case SettingType.STRING_LIST:
                if not isinstance(value, (list, tuple)) or not all(
                    isinstance(item, str) for item in value
                ):
                    raise self._error(value, "une liste de textes")
                return list(value)
        raise AssertionError(f"Type de réglage non géré : {self.type}")  # pragma: no cover

    def describe(self) -> dict[str, Any]:
        """Description sérialisable (pour l'interface)."""
        info: dict[str, Any] = {
            "key": self.key,
            "type": str(self.type),
            "label": self.label,
            "description": self.description,
            "default": self.default_value(),
        }
        if self.choices:
            info["choices"] = list(self.choices)
        if self.minimum is not None:
            info["minimum"] = float(self.minimum)
        if self.maximum is not None:
            info["maximum"] = float(self.maximum)
        return info

    def _check_range(self, value: float) -> None:
        if self.minimum is not None and value < self.minimum:
            raise InvalidSettingError(f"{self.key} : {value} est inférieur au minimum {self.minimum}")
        if self.maximum is not None and value > self.maximum:
            raise InvalidSettingError(f"{self.key} : {value} dépasse le maximum {self.maximum}")

    def _error(self, value: Any, expected: str) -> InvalidSettingError:
        return InvalidSettingError(f"{self.key} : {value!r} invalide, attendu {expected}")
