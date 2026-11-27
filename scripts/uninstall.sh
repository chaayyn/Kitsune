#!/usr/bin/env bash
# Retire ce que scripts/install.sh a installé. Les réglages (~/.config/saturn)
# et les données (~/.local/share/saturn) sont conservés.
set -euo pipefail

UUID="saturn@chaayyn.github.com"
DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"

if command -v gnome-extensions >/dev/null; then
    gnome-extensions disable "${UUID}" 2>/dev/null || true
fi
rm -f "${DATA_HOME}/gnome-shell/extensions/${UUID}"
rm -f "${DATA_HOME}"/dbus-1/services/org.saturn.{Daemon,Ui}.service
rm -f "${DATA_HOME}/fonts/SpaceGrotesk[wght].ttf"
for name in saturnd saturn; do
    if grep -q "scripts/install.sh" "${HOME}/.local/bin/${name}" 2>/dev/null; then
        rm -f "${HOME}/.local/bin/${name}"
    fi
done
echo "Saturn est désinstallé (réglages conservés dans ~/.config/saturn)."
