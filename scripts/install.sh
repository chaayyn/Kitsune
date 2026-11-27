#!/usr/bin/env bash
# Installe Saturn pour l'utilisateur courant, depuis ce dépôt (aucun sudo).
#
#  - ~/.local/bin/saturnd et ~/.local/bin/saturn : lanceurs vers ce dépôt
#  - activation D-Bus de org.saturn.Daemon : le démon démarre à la demande
#  - extension GNOME Shell (lien symbolique) et police Space Grotesk
#
# Relancer le script est sans danger. Désinstaller : scripts/uninstall.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UUID="saturn@chaayyn.github.com"
BIN_DIR="${HOME}/.local/bin"
DATA_HOME="${XDG_DATA_HOME:-${HOME}/.local/share}"
DBUS_DIR="${DATA_HOME}/dbus-1/services"
EXT_DIR="${DATA_HOME}/gnome-shell/extensions"
FONT_DIR="${DATA_HOME}/fonts"
PYTHON="$(command -v python3)"

step() { printf '\033[1;33m→\033[0m %s\n' "$*"; }

step "Lanceurs dans ${BIN_DIR}"
mkdir -p "${BIN_DIR}"
for pair in "saturnd:saturn" "saturn:saturn.ui"; do
    name="${pair%%:*}"
    module="${pair#*:}"
    cat > "${BIN_DIR}/${name}" <<EOF
#!/bin/sh
# Généré par ${REPO}/scripts/install.sh
export PYTHONPATH="${REPO}\${PYTHONPATH:+:\${PYTHONPATH}}"
exec "${PYTHON}" -m ${module} "\$@"
EOF
    chmod +x "${BIN_DIR}/${name}"
done

step "Activation D-Bus (démon et interface)"
mkdir -p "${DBUS_DIR}"
for pair in "org.saturn.Daemon:saturnd" "org.saturn.Ui:saturn"; do
    printf '[D-BUS Service]\nName=%s\nExec=%s\n' "${pair%%:*}" "${BIN_DIR}/${pair#*:}" \
        > "${DBUS_DIR}/${pair%%:*}.service"
done

step "Police Space Grotesk"
mkdir -p "${FONT_DIR}"
ln -sfn "${REPO}/assets/fonts/SpaceGrotesk[wght].ttf" "${FONT_DIR}/SpaceGrotesk[wght].ttf"
command -v fc-cache >/dev/null && fc-cache -f "${FONT_DIR}" >/dev/null || true

if command -v gnome-shell >/dev/null; then
    step "Extension GNOME Shell ${UUID}"
    mkdir -p "${EXT_DIR}"
    glib-compile-schemas "${REPO}/gnome-extension/${UUID}/schemas"
    ln -sfn "${REPO}/gnome-extension/${UUID}" "${EXT_DIR}/${UUID}"

    if gnome-extensions enable "${UUID}" 2>/dev/null; then
        echo "  Extension activée."
    else
        # GNOME Shell sous Wayland ne découvre une nouvelle extension qu'à la connexion :
        # on l'ajoute à la liste des extensions activées pour la prochaine session.
        current="$(gsettings get org.gnome.shell enabled-extensions)"
        if [[ "${current}" != *"'${UUID}'"* ]]; then
            if [[ "${current}" == "@as []" || "${current}" == "[]" ]]; then
                updated="['${UUID}']"
            else
                updated="${current%]*}, '${UUID}']"
            fi
            gsettings set org.gnome.shell enabled-extensions "${updated}"
        fi
        echo "  Extension prête : déconnectez-vous puis reconnectez-vous pour que GNOME la charge."
    fi
fi

echo
echo "Saturn est installé. Le démon démarre tout seul à la première demande."
