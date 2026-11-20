"""
vorssaint.ui.settings
~~~~~~~~~~~~~~~~~~~~~
Modern preferences window for Vorssaint.
Allows toggling individual modules on-demand, configuring general settings,
and viewing system diagnostics (Wayland/X11 capabilities).
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import TYPE_CHECKING
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QPushButton, QTabWidget, QWidget, QScrollArea, QFrame
)

from vorssaint.ui.theme import DARK_STYLESHEET
from vorssaint.ui.icons import IconManager

if TYPE_CHECKING:
    from vorssaint.core.app import VorssaintApp


class SettingsWindow(QDialog):
    def __init__(self, app: VorssaintApp) -> None:
        super().__init__()
        self.app = app
        self.setWindowTitle("Paramètres - Vorssaint")
        self.resize(650, 520)
        self.setStyleSheet(DARK_STYLESHEET)
        self.setWindowIcon(IconManager.get_app_icon())

        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        main_layout.setSpacing(14)

        # Header with Logo & Title
        header = QHBoxLayout()
        logo_label = QLabel()
        logo_label.setPixmap(IconManager.get_app_icon().pixmap(36, 36))
        header.addWidget(logo_label)

        title_box = QVBoxLayout()
        app_title = QLabel("Vorssaint pour Linux")
        app_title.setStyleSheet("font-size: 17px; font-weight: bold; color: #f4f4f5;")
        app_sub = QLabel("Boîte à outils modulaire, locale et respectueuse de la vie privée")
        app_sub.setStyleSheet("font-size: 12px; color: #a1a1aa;")
        title_box.addWidget(app_title)
        title_box.addWidget(app_sub)
        header.addLayout(title_box)

        header.addStretch()
        main_layout.addLayout(header)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._create_modules_tab(), "🧩 Modules")
        self.tabs.addTab(self._create_general_tab(), "⚙️ Général")
        self.tabs.addTab(self._create_diagnostics_tab(), "🔍 Diagnostics")
        main_layout.addWidget(self.tabs)

        # Footer
        footer = QHBoxLayout()
        footer.addStretch()
        close_btn = QPushButton("Fermer")
        close_btn.setObjectName("PrimaryButton")
        close_btn.clicked.connect(self.close)
        footer.addWidget(close_btn)
        main_layout.addLayout(footer)

    def _create_modules_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(10)
        scroll_layout.setContentsMargins(4, 4, 4, 4)

        modules = self.app.module_manager.get_all_modules()
        for module in modules:
            card = self._create_module_card(module)
            scroll_layout.addWidget(card)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)
        return container

    def _create_module_card(self, module) -> QFrame:
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #24242b;
                border: 1px solid #363642;
                border-radius: 10px;
                padding: 10px;
            }
        """)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(14)

        # Info Box
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        title_row = QHBoxLayout()
        name_label = QLabel(module.name)
        name_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #f4f4f5;")
        title_row.addWidget(name_label)

        cat_badge = QLabel(f"  {module.category.upper()}  ")
        cat_badge.setStyleSheet("""
            background-color: #312e81;
            color: #a5b4fc;
            border-radius: 4px;
            font-size: 10px;
            font-weight: bold;
        """)
        title_row.addWidget(cat_badge)
        title_row.addStretch()
        info_layout.addLayout(title_row)

        desc_label = QLabel(module.description)
        desc_label.setStyleSheet("font-size: 12px; color: #a1a1aa;")
        desc_label.setWordWrap(True)
        info_layout.addWidget(desc_label)

        supported, reason = module.is_supported()
        status_color = "#10b981" if supported else "#f59e0b"
        status_label = QLabel(f"● {reason}")
        status_label.setStyleSheet(f"font-size: 11px; color: {status_color};")
        info_layout.addWidget(status_label)

        layout.addLayout(info_layout, stretch=1)

        # Toggle Switch
        toggle = QCheckBox()
        toggle.setChecked(module.is_enabled)
        toggle.setEnabled(supported)
        toggle.setToolTip("Activer / Désactiver ce module")
        toggle.toggled.connect(lambda checked, mid=module.id: self._on_module_toggled(mid, checked))
        layout.addWidget(toggle)

        return card

    def _on_module_toggled(self, module_id: str, checked: bool) -> None:
        if checked:
            self.app.module_manager.enable_module(module_id)
        else:
            self.app.module_manager.disable_module(module_id)

    def _create_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Autostart checkbox
        autostart_box = QHBoxLayout()
        autostart_chk = QCheckBox("Lancer automatiquement Vorssaint au démarrage de la session")
        autostart_chk.setChecked(self.app.is_autostart_enabled())
        autostart_chk.toggled.connect(self._on_autostart_toggled)
        autostart_box.addWidget(autostart_chk)
        layout.addLayout(autostart_box)

        # Notifications checkbox
        notif_box = QHBoxLayout()
        notif_chk = QCheckBox("Activer les notifications système de bureau")
        notif_chk.setChecked(self.app.config_manager.get_value("notifications_enabled", True))
        notif_chk.toggled.connect(lambda chk: self.app.config_manager.set_value("notifications_enabled", chk))
        notif_box.addWidget(notif_chk)
        layout.addLayout(notif_box)

        layout.addStretch()
        return widget

    def _on_autostart_toggled(self, checked: bool) -> None:
        self.app.set_autostart(checked)

    def _create_diagnostics_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        env = self.app.env
        caps = env.get_capabilities()

        diag_items = [
            ("Type de session", caps.session_type.upper()),
            ("Environnement de bureau", caps.desktop_environment.capitalize()),
            ("systemd-inhibit (veille)", "Disponible" if caps.has_systemd_inhibit else "Non trouvé"),
            ("PipeWire (wpctl)", "Disponible" if caps.has_wpctl else "Non trouvé"),
            ("PulseAudio (pactl)", "Disponible" if caps.has_pactl else "Non trouvé"),
            ("D-Bus (gdbus)", "Disponible" if caps.has_gdbus else "Non trouvé"),
            ("wl-clipboard (Wayland)", "Disponible" if caps.has_wl_clipboard else "Non installé"),
            ("xclip (X11)", "Disponible" if caps.has_xclip else "Non installé"),
            ("notify-send (Notifications)", "Disponible" if caps.has_notify_send else "Non trouvé"),
        ]

        title = QLabel("Capacités et Détections Système")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #f4f4f5;")
        layout.addWidget(title)

        for label, val in diag_items:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #a1a1aa; font-size: 12px;")
            val_lbl = QLabel(val)
            val_color = "#10b981" if val in ("Disponible", "WAYLAND", "X11") else "#cbd5e1"
            val_lbl.setStyleSheet(f"font-weight: bold; font-size: 12px; color: {val_color};")
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val_lbl)
            layout.addLayout(row)

        layout.addStretch()
        return widget
