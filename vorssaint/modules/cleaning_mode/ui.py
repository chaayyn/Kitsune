"""
vorssaint.modules.cleaning_mode.ui
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Full-screen safe lock overlay for cleaning keyboards and screens.
Safely unlocks by holding Escape or the unlock button for 3 seconds.
"""

from __future__ import annotations
import time
from typing import TYPE_CHECKING
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton, QWidget
)

if TYPE_CHECKING:
    from vorssaint.modules.cleaning_mode.module import CleaningModeModule


class CleaningLockOverlay(QDialog):
    def __init__(self, module: CleaningModeModule) -> None:
        super().__init__()
        self.module = module
        self.setWindowTitle("Mode Nettoyage - Vorssaint")
        # Fullscreen overlay flags
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet("""
            QDialog {
                background-color: rgba(15, 15, 18, 0.94);
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
                font-family: sans-serif;
            }
            QProgressBar {
                border: 2px solid #3f3f46;
                border-radius: 8px;
                background-color: #27272a;
                text-align: center;
                color: #ffffff;
                height: 18px;
            }
            QProgressBar::chunk {
                background-color: #3b82f6;
                border-radius: 6px;
            }
            QPushButton {
                background-color: #ef4444;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:pressed {
                background-color: #dc2626;
            }
        """)

        self._esc_pressed_time: float = 0
        self._button_pressed_time: float = 0
        self._is_holding_esc = False
        self._is_holding_button = False

        self._timer = QTimer(self)
        self._timer.setInterval(50)  # 20 fps tick
        self._timer.timeout.connect(self._on_tick)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(24)

        icon_label = QLabel("✨")
        icon_label.setStyleSheet("font-size: 64px;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        title_label = QLabel("Mode Nettoyage Clavier & Écran Actif")
        title_label.setStyleSheet("font-size: 26px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        desc_label = QLabel("Toutes les frappes et clics sont sécurisés.\nNettoyez votre clavier et écran sans risque.")
        desc_label.setStyleSheet("font-size: 15px; color: #a1a1aa; line-height: 1.4;")
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(desc_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(320)
        layout.addWidget(self.progress_bar, alignment=Qt.AlignmentFlag.AlignCenter)

        self.status_label = QLabel("Maintenez Échap ou le bouton ci-dessous pendant 3s pour déverrouiller")
        self.status_label.setStyleSheet("font-size: 13px; color: #94a3b8;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        self.unlock_btn = QPushButton("Déverrouiller (Maintenir 3s)")
        self.unlock_btn.pressed.connect(self._on_btn_pressed)
        self.unlock_btn.released.connect(self._on_btn_released)
        layout.addWidget(self.unlock_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def showFullScreen(self) -> None:
        super().showFullScreen()
        self._timer.start()

    def _on_btn_pressed(self) -> None:
        self._is_holding_button = True
        self._button_pressed_time = time.time()

    def _on_btn_released(self) -> None:
        self._is_holding_button = False
        self.progress_bar.setValue(0)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if not self._is_holding_esc:
                self._is_holding_esc = True
                self._esc_pressed_time = time.time()
        # Absorb all other keys without closing or triggering actions
        event.accept()

    def keyReleaseEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._is_holding_esc = False
            self.progress_bar.setValue(0)
        event.accept()

    def _on_tick(self) -> None:
        hold_time = 0.0
        now = time.time()
        if self._is_holding_esc:
            hold_time = max(hold_time, now - self._esc_pressed_time)
        if self._is_holding_button:
            hold_time = max(hold_time, now - self._button_pressed_time)

        progress = min(100, int((hold_time / 3.0) * 100))
        self.progress_bar.setValue(progress)

        if hold_time >= 3.0:
            self._timer.stop()
            self.close()
            self.module.on_unlocked()
