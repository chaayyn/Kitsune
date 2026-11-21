"""
kitsune.modules.color_picker.ui
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Interactive color result preview dialog with HEX, RGB, HSL copies
and recent color history swatches.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, List
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QWidget
)

from kitsune.ui.theme import DARK_STYLESHEET

if TYPE_CHECKING:
    from kitsune.modules.color_picker.module import ColorPickerModule


class ColorSwatchWidget(QFrame):
    """Visual widget displaying the picked color with rounded corners and border."""
    def __init__(self, color_hex: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.color_hex = color_hex
        self.setFixedHeight(90)
        self.update_color(color_hex)

    def update_color(self, hex_val: str) -> None:
        self.color_hex = hex_val
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {hex_val};
                border: 2px solid #52525b;
                border-radius: 12px;
            }}
        """)


class ColorPreviewDialog(QDialog):
    """
    Popup dialog that visually displays the picked color,
    values in HEX / RGB / HSL with 1-click copy buttons,
    and a clickable history of recent colors.
    """
    def __init__(self, module: ColorPickerModule, hex_color: str, rgb_color: str, hsl_color: str) -> None:
        super().__init__()
        self.module = module
        self.hex_color = hex_color
        self.rgb_color = rgb_color
        self.hsl_color = hsl_color

        self.setWindowTitle("Couleur Prélevée - Kitsune")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(460, 480)
        self.setStyleSheet(DARK_STYLESHEET)

        self._init_ui()
        self.set_color(hex_color, rgb_color, hsl_color, auto_copy=False)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title_label = QLabel("🎨 Couleur Prélevée")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #f4f4f5;")
        header.addWidget(title_label)
        header.addStretch()

        self.status_badge = QLabel("✓ Copié dans le presse-papiers")
        self.status_badge.setStyleSheet("""
            background-color: #064e3b;
            color: #34d399;
            font-size: 11px;
            font-weight: bold;
            padding: 4px 10px;
            border-radius: 6px;
        """)
        header.addWidget(self.status_badge)
        layout.addLayout(header)

        # Color Swatch Preview Box
        self.swatch = ColorSwatchWidget(self.hex_color, self)
        layout.addWidget(self.swatch)

        # Field Rows: HEX, RGB, HSL
        self.hex_input = self._create_value_row("HEX", self.hex_color, layout)
        self.rgb_input = self._create_value_row("RGB", self.rgb_color, layout)
        self.hsl_input = self._create_value_row("HSL", self.hsl_color, layout)

        # Recent Color Palette / History
        history_title = QLabel("Historique récent :")
        history_title.setStyleSheet("font-size: 12px; font-weight: bold; color: #a1a1aa; margin-top: 6px;")
        layout.addWidget(history_title)

        self.history_layout = QHBoxLayout()
        self.history_layout.setSpacing(8)
        layout.addLayout(self.history_layout)
        self._refresh_history_swatches()

        layout.addStretch()

        # Action Buttons
        actions_layout = QHBoxLayout()
        pick_again_btn = QPushButton("🎯 Prélever à nouveau")
        pick_again_btn.setObjectName("PrimaryButton")
        pick_again_btn.clicked.connect(self._on_pick_again)
        actions_layout.addWidget(pick_again_btn)

        actions_layout.addStretch()

        close_btn = QPushButton("Fermer")
        close_btn.clicked.connect(self.close)
        actions_layout.addWidget(close_btn)

        layout.addLayout(actions_layout)

    def _create_value_row(self, label_text: str, default_val: str, parent_layout: QVBoxLayout) -> QLineEdit:
        row = QHBoxLayout()
        lbl = QLabel(f"{label_text} :")
        lbl.setFixedWidth(45)
        lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #cbd5e1;")
        row.addWidget(lbl)

        line_edit = QLineEdit(default_val)
        line_edit.setReadOnly(True)
        line_edit.setStyleSheet("font-size: 13px; font-family: monospace; font-weight: 500;")
        row.addWidget(line_edit)

        copy_btn = QPushButton("Copier")
        copy_btn.setFixedWidth(75)
        copy_btn.clicked.connect(lambda: self._copy_value(line_edit.text(), label_text))
        row.addWidget(copy_btn)

        parent_layout.addLayout(row)
        return line_edit

    def set_color(self, hex_val: str, rgb_val: str, hsl_val: str, auto_copy: bool = True) -> None:
        self.hex_color = hex_val
        self.rgb_color = rgb_val
        self.hsl_color = hsl_val

        self.swatch.update_color(hex_val)
        self.hex_input.setText(hex_val)
        self.rgb_input.setText(rgb_val)
        self.hsl_input.setText(hsl_val)

        if auto_copy:
            self._copy_value(hex_val, "HEX")

        self._refresh_history_swatches()

    def _copy_value(self, text: str, label: str) -> None:
        self.module.copy_color(text)
        self.status_badge.setText(f"✓ {label} copié !")
        self.status_badge.setStyleSheet("""
            background-color: #064e3b;
            color: #34d399;
            font-size: 11px;
            font-weight: bold;
            padding: 4px 10px;
            border-radius: 6px;
        """)

    def _refresh_history_swatches(self) -> None:
        # Clear existing
        while self.history_layout.count() > 0:
            item = self.history_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        history = self.module.get_history()
        if not history:
            no_hist = QLabel("(Aucun historique)")
            no_hist.setStyleSheet("color: #71717a; font-size: 11px;")
            self.history_layout.addWidget(no_hist)
            self.history_layout.addStretch()
            return

        for col in history[:9]:
            btn = QPushButton()
            btn.setFixedSize(32, 32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(f"Cliquer pour afficher et copier {col}")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {col};
                    border: 2px solid #52525b;
                    border-radius: 6px;
                }}
                QPushButton:hover {{
                    border: 2px solid #ffffff;
                }}
            """)
            btn.clicked.connect(lambda chk, c=col: self._on_history_clicked(c))
            self.history_layout.addWidget(btn)

        self.history_layout.addStretch()

    def _on_history_clicked(self, hex_val: str) -> None:
        # Calculate rgb & hsl for this history item
        rgb_str, hsl_str = self.module.calculate_formats(hex_val)
        self.set_color(hex_val, rgb_str, hsl_str, auto_copy=True)

    def _on_pick_again(self) -> None:
        self.hide()
        self.module.pick_color()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)
