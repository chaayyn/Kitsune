"""
vorssaint.modules.scratchpad.ui
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Floating sleek notepad with auto-save and quick copy.
"""

from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLabel
)

from vorssaint.ui.theme import DARK_STYLESHEET

if TYPE_CHECKING:
    from vorssaint.modules.scratchpad.module import ScratchpadModule


class ScratchpadWindow(QDialog):
    def __init__(self, module: ScratchpadModule, note_path: Path) -> None:
        super().__init__()
        self.module = module
        self.note_path = note_path
        self.setWindowTitle("Scratchpad - Vorssaint")
        self.resize(460, 380)
        self.setStyleSheet(DARK_STYLESHEET)
        if self.module.config.get("stay_on_top", True):
            self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)

        # Save debounce timer
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(800)  # Save 800ms after last keystroke
        self._save_timer.timeout.connect(self._save_content)

        self._init_ui()
        self._load_content()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        # Header
        header = QHBoxLayout()
        title = QLabel("📝 Bloc-notes rapide")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #f4f4f5;")
        header.addWidget(title)
        header.addStretch()

        copy_btn = QPushButton("Copier")
        copy_btn.setObjectName("PrimaryButton")
        copy_btn.clicked.connect(self._copy_all)
        header.addWidget(copy_btn)

        clear_btn = QPushButton("Effacer")
        clear_btn.setObjectName("DangerButton")
        clear_btn.clicked.connect(self._clear_content)
        header.addWidget(clear_btn)

        layout.addLayout(header)

        # Editor
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Écrivez vos notes temporaires, snippets, idées ici...")
        self.editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.editor)

        # Footer
        footer = QLabel("Sauvegarde automatique locale • Échap pour fermer")
        footer.setStyleSheet("color: #71717a; font-size: 11px;")
        layout.addWidget(footer)

    def _load_content(self) -> None:
        if self.note_path.exists():
            try:
                text = self.note_path.read_text(encoding="utf-8")
                self.editor.setPlainText(text)
            except Exception:
                pass

    def _save_content(self) -> None:
        try:
            self.note_path.parent.mkdir(parents=True, exist_ok=True)
            self.note_path.write_text(self.editor.toPlainText(), encoding="utf-8")
        except Exception as e:
            print(f"[Scratchpad] Save error: {e}")

    def _on_text_changed(self) -> None:
        self._save_timer.start()

    def _copy_all(self) -> None:
        text = self.editor.toPlainText()
        if text:
            self.module.app.clipboard().setText(text)
            self.module.app.env.send_notification("Scratchpad", "Contenu copié dans le presse-papiers.")

    def _clear_content(self) -> None:
        self.editor.clear()
        self._save_content()

    def closeEvent(self, event) -> None:
        self._save_content()
        super().closeEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)
