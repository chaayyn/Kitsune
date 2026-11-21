"""
kitsune.modules.clean_url.module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Clean URL Module.
Automatically removes tracking and analytics query parameters from copied URLs
(utm_*, fbclid, gclid, etc.) preserving privacy and clean sharing.
"""

from __future__ import annotations
import urllib.parse
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple
from PyQt6.QtGui import QAction, QClipboard
from PyQt6.QtWidgets import QMenu

from kitsune.core.module import BaseModule
from kitsune.ui.icons import IconManager

if TYPE_CHECKING:
    from kitsune.core.app import KitsuneApp


# Common tracking parameters to strip
DEFAULT_TRACKING_PARAMS: Set[str] = {
    # UTM
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "utm_reader", "utm_referrer", "utm_name", "utm_cid",
    # Facebook / Meta / Instagram
    "fbclid", "fbadid", "igshid",
    # Google
    "gclid", "gbraid", "wbraid", "_gl", "dclid",
    # Microsoft / Bing
    "msclkid",
    # Twitter / X
    "twclid",
    # TikTok
    "ttclid",
    # Newsletters / Marketing
    "mc_eid", "mc_cid", "_hsenc", "_hsmi", "vero_id", "vero_conv", "wickedid",
    # Other platforms
    "yclid", "spm", "ref_src", "si", "s_cid"
}


class CleanUrlModule(BaseModule):
    def __init__(self, app: KitsuneApp) -> None:
        super().__init__(app)
        self._last_cleaned_text: Optional[str] = None
        self._cleaned_count: int = 0
        self._tracking_params: Set[str] = set(DEFAULT_TRACKING_PARAMS)

    @property
    def id(self) -> str:
        return "clean_url"

    @property
    def name(self) -> str:
        return "Clean URL"

    @property
    def description(self) -> str:
        return "Nettoie automatiquement les paramètres de suivi (utm_*, fbclid...) des liens copiés."

    @property
    def category(self) -> str:
        return "clipboard"

    @property
    def icon_name(self) -> str:
        return "edit-clear"

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "notify_on_clean": True,
            "extra_params": [],
        }

    def on_enable(self) -> None:
        clipboard = self.app.clipboard()
        clipboard.dataChanged.connect(self._on_clipboard_changed)

    def on_disable(self) -> None:
        try:
            clipboard = self.app.clipboard()
            clipboard.dataChanged.disconnect(self._on_clipboard_changed)
        except Exception:
            pass

    def on_config_updated(self, config: Dict[str, Any]) -> None:
        extra = set(config.get("extra_params", []))
        self._tracking_params = DEFAULT_TRACKING_PARAMS.union(extra)

    def clean_url(self, raw_url: str) -> Tuple[str, bool, List[str]]:
        """
        Cleans tracking query parameters from an URL string.
        Returns (cleaned_url, was_cleaned, list_of_stripped_keys).
        """
        text = raw_url.strip()
        if not (text.startswith("http://") or text.startswith("https://")):
            return raw_url, False, []

        try:
            parsed = urllib.parse.urlsplit(text)
            if not parsed.query:
                return raw_url, False, []

            query_pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
            cleaned_pairs = []
            removed_keys = []

            for key, val in query_pairs:
                key_lower = key.lower()
                # Check if matches tracking param or utm_ prefix
                if key_lower in self._tracking_params or key_lower.startswith("utm_"):
                    removed_keys.append(key)
                else:
                    cleaned_pairs.append((key, val))

            if not removed_keys:
                return raw_url, False, []

            # Rebuild query string
            new_query = urllib.parse.urlencode(cleaned_pairs)
            new_parsed = parsed._replace(query=new_query)
            clean_result = urllib.parse.urlunsplit(new_parsed)

            return clean_result, True, removed_keys
        except Exception:
            return raw_url, False, []

    def _on_clipboard_changed(self) -> None:
        if not self.is_enabled:
            return

        clipboard = self.app.clipboard()
        text = clipboard.text(QClipboard.Mode.Clipboard)
        if not text or text == self._last_cleaned_text:
            return

        cleaned_text, was_cleaned, removed_keys = self.clean_url(text)
        if was_cleaned:
            self._last_cleaned_text = cleaned_text
            self._cleaned_count += 1

            # Update clipboard with clean link
            clipboard.setText(cleaned_text, QClipboard.Mode.Clipboard)

            if self._config.get("notify_on_clean", True):
                params_str = ", ".join(removed_keys[:3])
                if len(removed_keys) > 3:
                    params_str += f" (+{len(removed_keys)-3})"
                self.app.env.send_notification(
                    "Lien nettoyé",
                    f"Paramètres supprimés : {params_str}\n{cleaned_text[:60]}...",
                    icon="emblem-default"
                )

            self.state_changed.emit()

    def get_status_summary(self) -> str:
        if not self.is_enabled:
            return "Désactivé"
        return f"Actif ({self._cleaned_count} liens nettoyés)"

    def get_tray_actions(self, parent_menu: QMenu) -> List[QAction | QMenu]:
        if not self.is_enabled:
            return []

        menu = QMenu(f"🔗 Clean URL ({self._cleaned_count} nettoyés)", parent_menu)
        menu.setIcon(IconManager.get_icon("edit-clear", fallback_color="#10b981", fallback_symbol="🧹"))

        notify_act = QAction("Notification lors du nettoyage", menu)
        notify_act.setCheckable(True)
        notify_act.setChecked(self._config.get("notify_on_clean", True))
        notify_act.triggered.connect(self._toggle_notify)
        menu.addAction(notify_act)

        return [menu]

    def _toggle_notify(self, checked: bool) -> None:
        self._config["notify_on_clean"] = checked
        self.app.config_manager.set_module_config(self.id, self._config)
