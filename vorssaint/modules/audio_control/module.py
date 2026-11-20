"""
vorssaint.modules.audio_control.module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Audio Control & Global Mic Mute Module.
Integrates with PipeWire (wpctl) and PulseAudio (pactl) to provide
instant mic mute toggle and quick audio output sink switching.
"""

from __future__ import annotations
import re
import subprocess
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu

from vorssaint.core.module import BaseModule
from vorssaint.ui.icons import IconManager

if TYPE_CHECKING:
    from vorssaint.core.app import VorssaintApp


class AudioControlModule(BaseModule):
    def __init__(self, app: VorssaintApp) -> None:
        super().__init__(app)
        self._backend: Optional[str] = None  # 'wpctl' or 'pactl'

    @property
    def id(self) -> str:
        return "audio_control"

    @property
    def name(self) -> str:
        return "Contrôle Audio & Micro"

    @property
    def description(self) -> str:
        return "Mute micro global en 1 clic et bascule rapide de la sortie audio (PipeWire / PulseAudio)."

    @property
    def category(self) -> str:
        return "audio"

    @property
    def icon_name(self) -> str:
        return "audio-volume-high"

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "notify_on_mute": True,
        }

    def is_supported(self) -> Tuple[bool, str]:
        env = self.app.env
        if env.has_tool("wpctl"):
            self._backend = "wpctl"
            return True, "Supporté via PipeWire (wpctl)"
        elif env.has_tool("pactl"):
            self._backend = "pactl"
            return True, "Supporté via PulseAudio (pactl)"
        return False, "Nécessite 'wpctl' (PipeWire) ou 'pactl' (PulseAudio)"

    def on_enable(self) -> None:
        if not self._backend:
            self.is_supported()

    def get_audio_info(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Returns (sinks, sources) lists from wpctl or pactl."""
        if self._backend == "wpctl":
            return self._get_wpctl_info()
        elif self._backend == "pactl":
            return self._get_pactl_info()
        return [], []

    def _get_wpctl_info(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        try:
            out = subprocess.check_output(["wpctl", "status"], text=True, stderr=subprocess.DEVNULL)
        except Exception:
            return [], []

        sinks = []
        sources = []
        current_section = None

        for line in out.splitlines():
            if "Sinks:" in line:
                current_section = "sinks"
                continue
            elif "Sources:" in line:
                current_section = "sources"
                continue
            elif any(k in line for k in ("Filters:", "Streams:", "Video", "Settings")):
                current_section = None
                continue

            if current_section in ("sinks", "sources"):
                # Line format: │  *   46. Device Name [vol: 1.00 MUTED]
                m = re.search(r'([* ])\s+(\d+)\.\s+(.*?)\s+\[vol:\s*([\d\.]+)(?:\s+(MUTED))?\]', line)
                if m:
                    is_default = m.group(1) == '*'
                    dev_id = int(m.group(2))
                    name = m.group(3).strip()
                    vol = float(m.group(4))
                    is_muted = bool(m.group(5))
                    entry = {
                        "id": dev_id,
                        "name": name,
                        "volume": vol,
                        "is_muted": is_muted,
                        "is_default": is_default,
                    }
                    if current_section == "sinks":
                        sinks.append(entry)
                    else:
                        sources.append(entry)

        return sinks, sources

    def _get_pactl_info(self) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        # Basic pactl fallback
        return [], []

    def is_mic_muted(self) -> bool:
        _, sources = self.get_audio_info()
        for src in sources:
            if src.get("is_default"):
                return bool(src.get("is_muted"))
        return False

    def toggle_mic_mute(self) -> bool:
        """Toggles global default microphone mute."""
        try:
            if self._backend == "wpctl":
                subprocess.run(
                    ["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "toggle"],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            elif self._backend == "pactl":
                subprocess.run(
                    ["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "toggle"],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            muted = self.is_mic_muted()
            if self._config.get("notify_on_mute", True):
                state_str = "MUET (Coupé)" if muted else "ACTIF (Activé)"
                icon = "microphone-sensitivity-muted" if muted else "audio-input-microphone"
                self.app.env.send_notification("Microphone", f"Le micro est maintenant : {state_str}", icon=icon)

            self.state_changed.emit()
            return True
        except Exception as e:
            print(f"[AudioControl] Error toggling mic: {e}")
            return False

    def set_default_sink(self, sink_id: int) -> bool:
        """Switches default audio output device."""
        try:
            if self._backend == "wpctl":
                subprocess.run(
                    ["wpctl", "set-default", str(sink_id)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                self.app.env.send_notification("Sortie Audio", "Périphérique de sortie audio modifié.")
                self.state_changed.emit()
                return True
        except Exception as e:
            print(f"[AudioControl] Error setting sink {sink_id}: {e}")
        return False

    def get_status_summary(self) -> str:
        if not self.is_enabled:
            return "Désactivé"
        sinks, sources = self.get_audio_info()
        default_sink = next((s["name"] for s in sinks if s["is_default"]), "Inconnu")
        mic_status = "Micro Muet" if self.is_mic_muted() else "Micro Actif"
        return f"{mic_status} • {default_sink[:20]}"

    def get_tray_actions(self, parent_menu: QMenu) -> List[QAction | QMenu]:
        if not self.is_enabled:
            return []

        sinks, sources = self.get_audio_info()
        mic_muted = self.is_mic_muted()

        actions: List[QAction | QMenu] = []

        # 1. Quick Mic Mute Toggle Action
        mic_label = "🔴 Microphone : MUET (Cliquez pour réactiver)" if mic_muted else "🟢 Microphone : ACTIF (Cliquez pour couper)"
        mic_act = QAction(mic_label, parent_menu)
        mic_act.triggered.connect(self.toggle_mic_mute)
        actions.append(mic_act)

        # 2. Output Sink Submenu
        default_sink = next((s for s in sinks if s["is_default"]), None)
        sink_title = f"🔊 Sortie : {default_sink['name'][:22]}..." if default_sink else "🔊 Sortie Audio"
        sink_menu = QMenu(sink_title, parent_menu)
        sink_menu.setIcon(IconManager.get_icon("audio-volume-high", fallback_color="#06b6d4", fallback_symbol="🔊"))

        for sink in sinks:
            is_def = sink.get("is_default", False)
            vol_pct = int(sink.get("volume", 0) * 100)
            prefix = "✓ " if is_def else "   "
            item_act = QAction(f"{prefix}{sink['name']} ({vol_pct}%)", sink_menu)
            if not is_def:
                item_act.triggered.connect(lambda chk, sid=sink['id']: self.set_default_sink(sid))
            sink_menu.addAction(item_act)

        actions.append(sink_menu)
        return actions
