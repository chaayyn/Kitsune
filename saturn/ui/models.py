"""Modèles Qt exposés au QML : liste des modules et réglages d'un module."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, QPersistentModelIndex, Qt, Property, Signal, Slot

#: Ordre d'affichage et libellés des catégories.
CATEGORIES: dict[str, str] = {
    "clipboard": "Presse-papiers",
    "tools": "Outils",
    "system": "Système",
    "sound": "Son",
    "windows": "Fenêtres",
    "energy": "Énergie",
    "capture": "Capture",
}
_CATEGORY_ORDER = {key: rank for rank, key in enumerate(CATEGORIES)}

Index = QModelIndex | QPersistentModelIndex


def module_status(module: Mapping[str, Any]) -> str:
    """Résumé de l'état : ``running``, ``off``, ``unavailable``, ``error`` ou ``starting``."""
    if module.get("enabled"):
        if module.get("running"):
            return "running"
        if not module.get("available", True):
            return "unavailable"
        return "error" if module.get("error") else "starting"
    if not module.get("available", True):
        return "unavailable"
    return "off"


def _sort_key(module: Mapping[str, Any]) -> tuple[int, str]:
    return (_CATEGORY_ORDER.get(module.get("category", ""), len(CATEGORIES)), module.get("name", "").lower())


class _RoleModel(QAbstractListModel):
    """Base : chaque ligne est un ``dict`` ; les rôles sont ses clés."""

    ROLES: tuple[str, ...] = ()
    countChanged = Signal()

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []
        self._role_ids = {Qt.ItemDataRole.UserRole + 1 + i: name for i, name in enumerate(self.ROLES)}
        self.modelReset.connect(self.countChanged)
        self.rowsInserted.connect(self.countChanged)
        self.rowsRemoved.connect(self.countChanged)

    def roleNames(self) -> dict[int, QByteArray]:
        return {role: QByteArray(name.encode()) for role, name in self._role_ids.items()}

    def rowCount(self, parent: Index = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: Index, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        name = self._role_ids.get(role)
        return self._rows[index.row()].get(name) if name else None

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._rows)

    @Slot(int, result="QVariantMap")
    def get(self, row: int) -> dict[str, Any]:
        return dict(self._rows[row]) if 0 <= row < len(self._rows) else {}

    def rows(self) -> list[dict[str, Any]]:
        return [dict(row) for row in self._rows]

    def clear(self) -> None:
        self.beginResetModel()
        self._rows = []
        self.endResetModel()

    def _emit_row_changed(self, row: int) -> None:
        index = self.index(row, 0)
        self.dataChanged.emit(index, index, list(self._role_ids))


class ModuleListModel(_RoleModel):
    ROLES = (
        "moduleId",
        "name",
        "description",
        "category",
        "categoryLabel",
        "isEnabled",
        "running",
        "available",
        "missing",
        "error",
        "actions",
        "status",
        "pending",
    )
    activeCountChanged = Signal()

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.countChanged.connect(self.activeCountChanged)
        self.dataChanged.connect(lambda *_: self.activeCountChanged.emit())

    @Property(int, notify=activeCountChanged)
    def activeCount(self) -> int:
        return sum(1 for row in self._rows if row["status"] == "running")

    def reset(self, modules: Iterable[Mapping[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = sorted((self._row(m) for m in modules), key=_sort_key)
        self.endResetModel()

    def update(self, module: Mapping[str, Any]) -> None:
        """Met à jour (ou insère à sa place) un module reçu du démon."""
        row = self._row(module)
        current = self.row_of(row["moduleId"])
        if current >= 0:
            self._rows[current] = row
            self._emit_row_changed(current)
            return
        position = sum(1 for existing in self._rows if _sort_key(existing) < _sort_key(row))
        self.beginInsertRows(QModelIndex(), position, position)
        self._rows.insert(position, row)
        self.endInsertRows()

    def set_pending(self, module_id: str, pending: bool) -> None:
        row = self.row_of(module_id)
        if row >= 0 and self._rows[row]["pending"] != pending:
            self._rows[row]["pending"] = pending
            self._emit_row_changed(row)

    def row_of(self, module_id: str) -> int:
        for row, module in enumerate(self._rows):
            if module["moduleId"] == module_id:
                return row
        return -1

    def module(self, module_id: str) -> dict[str, Any] | None:
        row = self.row_of(module_id)
        return dict(self._rows[row]) if row >= 0 else None

    @staticmethod
    def _row(module: Mapping[str, Any]) -> dict[str, Any]:
        category = str(module.get("category", ""))
        return {
            "moduleId": str(module.get("id", "")),
            "name": str(module.get("name", "")),
            "description": str(module.get("description", "")),
            "category": category,
            "categoryLabel": CATEGORIES.get(category, category.capitalize() or "Autres"),
            "isEnabled": bool(module.get("enabled", False)),
            "running": bool(module.get("running", False)),
            "available": bool(module.get("available", True)),
            "missing": list(module.get("missing", [])),
            "error": str(module.get("error", "")),
            "actions": list(module.get("actions", [])),
            "status": module_status(module),
            "pending": False,
        }


class SettingsModel(_RoleModel):
    """Réglages du module sélectionné, construits à partir du schéma du démon."""

    ROLES = (
        "key",
        "type",
        "signature",
        "label",
        "description",
        "value",
        "defaultValue",
        "isDefault",
        "choices",
        "minimum",
        "maximum",
        "hasMinimum",
        "hasMaximum",
    )

    def load(self, schema: Iterable[Mapping[str, Any]], values: Mapping[str, Any]) -> None:
        rows = []
        for entry in schema:
            key = str(entry["key"])
            default = entry.get("default")
            value = values.get(key, default)
            rows.append(
                {
                    "key": key,
                    "type": str(entry.get("type", "string")),
                    "signature": str(entry.get("signature", "s")),
                    "label": str(entry.get("label", key)),
                    "description": str(entry.get("description", "")),
                    "value": value,
                    "defaultValue": default,
                    "isDefault": value == default,
                    "choices": list(entry.get("choices", [])),
                    "minimum": float(entry.get("minimum", 0.0)),
                    "maximum": float(entry.get("maximum", 0.0)),
                    "hasMinimum": "minimum" in entry,
                    "hasMaximum": "maximum" in entry,
                }
            )
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def set_value(self, key: str, value: Any) -> None:
        row = self.row_of(key)
        if row < 0:
            return
        entry = self._rows[row]
        entry["value"] = value
        entry["isDefault"] = value == entry["defaultValue"]
        self._emit_row_changed(row)

    def refresh(self, key: str) -> None:
        """Ré-émet la ligne pour que le QML annule une saisie refusée."""
        row = self.row_of(key)
        if row >= 0:
            self._emit_row_changed(row)

    def signature(self, key: str) -> str | None:
        row = self.row_of(key)
        return self._rows[row]["signature"] if row >= 0 else None

    def value(self, key: str) -> Any:
        row = self.row_of(key)
        return self._rows[row]["value"] if row >= 0 else None

    def row_of(self, key: str) -> int:
        for row, entry in enumerate(self._rows):
            if entry["key"] == key:
                return row
        return -1
