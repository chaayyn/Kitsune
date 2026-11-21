"""
kitsune.ui.icons
~~~~~~~~~~~~~~~~~~
Icon provider with automatic SVG loading and QPainter fallback generation.
Guarantees clean icons on any Linux desktop regardless of theme.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Optional
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush, QFont
from PyQt6.QtCore import Qt, QRectF

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "icons"


class IconManager:
    _cache: dict[str, QIcon] = {}

    @classmethod
    def get_app_icon(cls) -> QIcon:
        return cls.get_icon("kitsune", fallback_color="#f97316", fallback_symbol="🦊")

    @classmethod
    def get_icon(cls, name: str, fallback_color: str = "#3b82f6", fallback_symbol: str = "•") -> QIcon:
        if name in cls._cache:
            return cls._cache[name]

        svg_path = ASSETS_DIR / f"{name}.svg"
        if svg_path.exists():
            icon = QIcon(str(svg_path))
            if not icon.isNull():
                cls._cache[name] = icon
                return icon

        # Check system theme
        system_icon = QIcon.fromTheme(name)
        if not system_icon.isNull():
            cls._cache[name] = system_icon
            return system_icon

        # Generate procedural crisp icon
        icon = cls.create_symbol_icon(fallback_symbol, fallback_color)
        cls._cache[name] = icon
        return icon

    @classmethod
    def create_symbol_icon(cls, symbol: str, bg_color: str = "#3b82f6", text_color: str = "#ffffff") -> QIcon:
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw rounded background circle
        painter.setBrush(QBrush(QColor(bg_color)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(2, 2, 28, 28), 7, 7)

        # Draw symbol
        painter.setPen(QColor(text_color))
        font = QFont("Sans-Serif", 13, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(QRectF(0, 0, 32, 32), Qt.AlignmentFlag.AlignCenter, symbol)
        painter.end()

        return QIcon(pixmap)
