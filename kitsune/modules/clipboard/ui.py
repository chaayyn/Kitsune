"""
kitsune.modules.clipboard.ui
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Searchable popup window for clipboard history.
Press Enter or click to copy any item back to clipboard.
"""

from __future__ import annotations
import datetime
from typing import TYPE_CHECKING
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QLabel, QWidget
)

from kitsune.ui.theme import DARK_STYLESHEET

if TYPE_CHECKING:
    from kitsune.modules.clipboard.module import ClipboardModule


class ClipboardWindow(QDialog):
    item_selected = pyqtSignal(str)

    def __init__(self, module: ClipboardModule) -> None:
        super().__init__()
        self.module = module
        self.setWindowTitle("Historique Presse-papiers - Kitsune")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(540, 480)
        self.setStyleSheet(DARK_STYLESHEET)

        self._init_ui()
        self.refresh_list()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel("📋 Historique du Presse-papiers")
        title_label.setStyleSheet("font-size: 15px; font-weight: bold; color: #f4f4f5;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        clear_btn = QPushButton("Vider")
        clear_btn.setObjectName("DangerButton")
        clear_btn.clicked.connect(self._on_clear_clicked)
        header_layout.addWidget(clear_btn)
        layout.addLayout(header_layout)

        # Search box
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 Rechercher dans l'historique...")
        self.search_edit.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_edit)

        # List widget
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget)

        # Footer instructions
        footer_label = QLabel("Double-cliquez ou appuyez sur Entrée pour copier • Échap pour fermer")
        footer_label.setStyleSheet("color: #71717a; font-size: 11px;")
        layout.addWidget(footer_label)

    def refresh_list(self) -> None:
        query = self.search_edit.text().strip()
        items = self.module.storage.get_recent(limit=100, search_query=query)

        self.list_widget.clear()
        for item_id, content, created_at in items:
            dt = datetime.datetime.fromtimestamp(created_at).strftime("%H:%M:%S")
            # Format preview text (single line, max 90 chars)
            clean_preview = " ".join(content.split())
            if len(clean_preview) > 90:
                clean_preview = clean_preview[:90] + "..."

            display_text = f"[{dt}]  {clean_preview}"
            list_item = QListWidgetItem(display_text)
            list_item.setData(Qt.ItemDataRole.UserRole, content)
            list_item.setData(Qt.ItemDataRole.UserRole + 1, item_id)
            self.list_widget.addItem(list_item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _on_search_changed(self, text: str) -> None:
        self.refresh_list()

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        content = item.data(Qt.ItemDataRole.UserRole)
        if content:
            self.item_selected.emit(content)
            self.close()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            item = self.list_widget.currentItem()
            if item:
                self._on_item_double_clicked(item)
                return
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def _on_clear_clicked(self) -> None:
        self.module.storage.clear()
        self.refresh_list()
