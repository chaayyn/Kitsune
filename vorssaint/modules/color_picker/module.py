"""
vorssaint.modules.color_picker.module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Screen Color Picker Module.
Uses Freedesktop XDG Desktop Portal (org.freedesktop.portal.Screenshot.PickColor)
with live signal subscription and visual preview dialog.
Compatible with modern Wayland (GNOME, KDE) and X11 desktops.
"""

from __future__ import annotations
import colorsys
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction, QClipboard, QIcon, QPixmap, QColor
from PyQt6.QtWidgets import QMenu

from vorssaint.core.module import BaseModule
from vorssaint.modules.color_picker.ui import ColorPreviewDialog
from vorssaint.ui.icons import IconManager

if TYPE_CHECKING:
    from vorssaint.core.app import VorssaintApp


class ColorPickerModule(BaseModule):
    def __init__(self, app: VorssaintApp) -> None:
        super().__init__(app)
        self._last_color: Optional[str] = None
        self._last_rgb: Optional[str] = None
        self._last_hsl: Optional[str] = None
        self._history: List[str] = []
        self._dialog: Optional[ColorPreviewDialog] = None
        self._bus: Optional[Gio.DBusConnection] = None

    @property
    def id(self) -> str:
        return "color_picker"

    @property
    def name(self) -> str:
        return "Color Picker"

    @property
    def description(self) -> str:
        return "Pipette écran avec aperçu visuel, historique et formats HEX / RGB / HSL (Wayland/X11)."

    @property
    def category(self) -> str:
        return "system"

    @property
    def icon_name(self) -> str:
        return "color-picker"

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "format": "hex",
            "show_preview_window": True,
            "history": [],
        }

    def is_supported(self) -> Tuple[bool, str]:
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            if bus is not None:
                return True, "Supporté via XDG Desktop Portal (PickColor)"
        except Exception as e:
            return False, f"D-Bus inaccessible: {e}"
        return False, "Portail XDG non disponible"

    def on_enable(self) -> None:
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception as e:
            print(f"[ColorPicker] Failed to connect to session bus: {e}")
        self._history = list(self._config.get("history", []))
        if self._history:
            self._last_color = self._history[0]
            self._last_rgb, self._last_hsl = self.calculate_formats(self._last_color)

    def on_disable(self) -> None:
        if self._dialog is not None:
            self._dialog.close()
            self._dialog = None

    def pick_color(self) -> None:
        """Invokes the XDG Desktop Portal PickColor interface and listens for the response."""
        if self._bus is None:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)

        try:
            # Request color picking from portal
            res = self._bus.call_sync(
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.Screenshot",
                "PickColor",
                GLib.Variant("(sa{sv})", ("", {})),
                GLib.VariantType("(o)"),
                Gio.DBusCallFlags.NONE,
                -1,
                None
            )
            handle = res.unpack()[0]

            # Subscribe to the Response signal specifically on this request handle
            sub_id = self._bus.signal_subscribe(
                "org.freedesktop.portal.Desktop",
                "org.freedesktop.portal.Request",
                "Response",
                handle,
                None,
                Gio.DBusSignalFlags.NONE,
                self._on_portal_response,
                None
            )

            self.app.env.send_notification(
                "Pipette Couleur",
                "Cliquez n'importe où sur l'écran pour sélectionner une couleur...",
                icon="color-picker"
            )
        except Exception as e:
            print(f"[ColorPicker] Error calling PickColor portal: {e}")
            self.app.env.send_notification(
                "Erreur Color Picker",
                f"Impossible de lancer la pipette : {e}",
                icon="dialog-error"
            )

    def _on_portal_response(self, connection, sender, path, interface, signal, parameters, user_data) -> None:
        """Callback invoked when portal returns the selected color."""
        try:
            code, results = parameters.unpack()
            if code == 0 and "color" in results:
                color_tuple = results["color"]
                if hasattr(color_tuple, "unpack"):
                    color_tuple = color_tuple.unpack()

                # RGB doubles are in 0.0 - 1.0 range
                r = int(round(color_tuple[0] * 255))
                g = int(round(color_tuple[1] * 255))
                b = int(round(color_tuple[2] * 255))

                hex_val = f"#{r:02X}{g:02X}{b:02X}"
                rgb_val = f"rgb({r}, {g}, {b})"
                h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
                hsl_val = f"hsl({int(round(h * 360))}°, {int(round(s * 100))}%, {int(round(l * 100))}%)"

                # Dispatch onto Qt event queue safely
                QTimer.singleShot(0, lambda: self._on_color_picked_success(hex_val, rgb_val, hsl_val))
            elif code == 1:
                # User cancelled
                pass
        except Exception as e:
            print(f"[ColorPicker] Response error: {e}")

    def _on_color_picked_success(self, hex_val: str, rgb_val: str, hsl_val: str) -> None:
        self._last_color = hex_val
        self._last_rgb = rgb_val
        self._last_hsl = hsl_val

        # Add to history
        if hex_val in self._history:
            self._history.remove(hex_val)
        self._history.insert(0, hex_val)
        self._history = self._history[:12]  # keep 12 recent

        # Save history in config
        self._config["history"] = self._history
        self.app.config_manager.set_module_config(self.id, self._config)

        # Copy to clipboard
        self.copy_color(hex_val)

        # Notification
        self.app.env.send_notification(
            f"Couleur : {hex_val}",
            f"{rgb_val} • {hsl_val}\nCopié dans le presse-papiers !",
            icon="color-picker"
        )

        # Show visual preview window
        if self._config.get("show_preview_window", True):
            self.show_preview_dialog(hex_val, rgb_val, hsl_val)

        self.state_changed.emit()

    def show_preview_dialog(self, hex_val: Optional[str] = None, rgb_val: Optional[str] = None, hsl_val: Optional[str] = None) -> None:
        """Opens or updates the visual color preview dialog."""
        target_hex = hex_val or self._last_color or "#3B82F6"
        target_rgb = rgb_val or self._last_rgb or "rgb(59, 130, 246)"
        target_hsl = hsl_val or self._last_hsl or "hsl(217°, 91%, 60%)"

        if self._dialog is None:
            self._dialog = ColorPreviewDialog(self, target_hex, target_rgb, target_hsl)
        else:
            self._dialog.set_color(target_hex, target_rgb, target_hsl, auto_copy=False)

        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()

    def copy_color(self, value: str) -> None:
        """Copies text to clipboard."""
        self.app.clipboard().setText(value, QClipboard.Mode.Clipboard)

    def get_history(self) -> List[str]:
        return list(self._history)

    def calculate_formats(self, hex_val: str) -> Tuple[str, str]:
        """Calculates (rgb_str, hsl_str) from a HEX string."""
        clean = hex_val.lstrip("#")
        if len(clean) != 6:
            return "rgb(0, 0, 0)", "hsl(0°, 0%, 0%)"
        r = int(clean[0:2], 16)
        g = int(clean[2:4], 16)
        b = int(clean[4:6], 16)
        rgb_str = f"rgb({r}, {g}, {b})"
        h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
        hsl_str = f"hsl({int(round(h * 360))}°, {int(round(s * 100))}%, {int(round(l * 100))}%)"
        return rgb_str, hsl_str

    def _create_color_icon(self, hex_val: str) -> QIcon:
        """Creates a crisp square color swatch icon for the tray menu."""
        pixmap = QPixmap(18, 18)
        pixmap.fill(QColor(hex_val))
        return QIcon(pixmap)

    def get_status_summary(self) -> str:
        if not self.is_enabled:
            return "Désactivé"
        if self._last_color:
            return f"Actif ({self._last_color})"
        return "Prêt"

    def get_tray_actions(self, parent_menu: QMenu) -> List[QAction | QMenu]:
        if not self.is_enabled:
            return []

        menu = QMenu("🎨 Color Picker", parent_menu)
        menu.setIcon(IconManager.get_icon("color-picker", fallback_color="#ec4899", fallback_symbol="🎨"))

        # 1. Main Pick Action
        pick_act = QAction("🎯 Prélever une couleur (Pipette)...", menu)
        pick_act.triggered.connect(self.pick_color)
        menu.addAction(pick_act)

        # 2. Last Color Action with live visual preview swatch!
        if self._last_color:
            menu.addSeparator()
            last_act = QAction(f"Dernière couleur : {self._last_color}", menu)
            last_act.setIcon(self._create_color_icon(self._last_color))
            last_act.setToolTip("Ouvrir la fenêtre d'aperçu de la couleur")
            last_act.triggered.connect(lambda: self.show_preview_dialog())
            menu.addAction(last_act)

        # 3. History Submenu with swatches
        if self._history:
            hist_menu = QMenu("Historique des couleurs", menu)
            for col in self._history[:8]:
                rgb, hsl = self.calculate_formats(col)
                item = QAction(f"{col} ({rgb})", hist_menu)
                item.setIcon(self._create_color_icon(col))
                item.triggered.connect(lambda chk, c=col, r=rgb, h=hsl: self.show_preview_dialog(c, r, h))
                hist_menu.addAction(item)
            menu.addMenu(hist_menu)

        return [menu]
