# Vorssaint pour Linux ⚡

Équivalent modulaire, léger et *local-first* de [Vorssaint](https://vorssaint.com/fr/) conçu pour les environnements de bureau Linux modernes (**Wayland** et **X11**).

Vorssaint réside discrètement dans la zone de notification (*system tray* / barre supérieure) et permet d'activer ou désactiver chaque module indépendamment. **Aucune télémétrie, aucune ressource consommée pour les fonctions désactivées.**

---

## 🌟 Fonctionnalités & Modules

| Module | Catégorie | Description | Cible Linux / Dépendance |
|---|---|---|---|
| ☕ **Keep Awake** | Énergie | Empêche la mise en veille et l'extinction de l'écran (15m, 30m, 1h, 2h ou illimité). | `systemd-inhibit` / D-Bus |
| 🔗 **Clean URL** | Presse-papiers | Nettoie automatiquement les paramètres de pistage (`utm_*`, `fbclid`, `gclid`, `si`...) des liens copiés. | Natif Python (`urllib`) |
| 📋 **Historique Presse-papiers** | Presse-papiers | Historique local SQLite, recherche instantanée en fenêtre flottante, protection contre la mémorisation de secrets / clés privées. | Natif SQLite3 + `QClipboard` |
| 🎤 **Contrôle Audio & Micro** | Audio | Coupure micro globale en 1 clic et bascule rapide de la sortie audio (casque / haut-parleurs). | PipeWire (`wpctl`) ou PulseAudio (`pactl`) |
| 📝 **Scratchpad** | Productivité | Bloc-notes éphémère flottant avec sauvegarde automatique locale. | Natif |
| 🎨 **Color Picker** | Productivité | Pipette de prélèvement de couleur d'écran avec formats HEX/RGB/HSL. | XDG Desktop Portal (Wayland/X11) |
| ✨ **Mode Nettoyage** | Système | Verrouille temporairement le clavier et l'écran pour les nettoyer sans risque de frappe accidentelle (déverrouillage par maintien d'Échap 3s). | Écran de capture Qt |
| 📊 **Métriques Système** | Système | Moniteur léger en direct de la charge CPU et RAM (désactivé par défaut). | Lecture directe `/proc/stat` & `/proc/meminfo` |

---

## 🏗️ Architecture & Choix Technique

### Pourquoi Python 3 + PyQt6 ?
1. **Support Wayland / X11 StatusNotifierItem (SNI)** : Contrairement à GTK4 qui a totalement supprimé la prise en charge native des barres d'état (`GtkStatusIcon`), PyQt6 implémente nativement le protocole D-Bus Freedesktop `StatusNotifierItem` sur Wayland (GNOME avec l'extension AppIndicator, KDE Plasma, Sway, Hyprland via Waybar, etc.) et X11.
2. **Empreinte mémoire minimale** : Moins de 35 Mo de RAM en cours d'exécution (contrairement aux solutions Electron/Tauri nécessitant un moteur Chromium complet).
3. **Zéro compilation & Extensibilité immédiate** : Architecture modulaire à base de `BaseModule` permettant à n'importe quel contributeur d'ajouter un module en quelques dizaines de lignes de Python sans chaîne de compilation C/Rust complexe.
4. **Intégration directe aux standards Linux** :
   - D-Bus pour les inhibitions de veille et le portail de sélection de couleurs.
   - PipeWire / WirePlumber (`wpctl`) pour l'audio sans latence.
   - Données stockées localement selon la norme XDG (`~/.config/vorssaint/` et `~/.local/share/vorssaint/`).

---

## 📋 Prérequis & Dépendances Système

Sur une distribution basée sur Debian/Ubuntu/Kali :
```bash
sudo apt update
sudo apt install python3 python3-pyqt6
```

Outils système recommandés (généralement déjà présents par défaut) :
- **PipeWire / WirePlumber** (`wpctl`) : pour le module Audio.
- **systemd** (`systemd-inhibit`) : pour le module Keep Awake.
- **xdg-desktop-portal** : pour le Color Picker sous Wayland.
- **libnotify-bin** (`notify-send`) : pour les notifications de bureau.

---

## 🚀 Installation & Lancement

### Lancement direct
```bash
git clone git@github.com:chaayyn/vorssaint-linux.git
cd vorssaint-linux
python3 run.py
```

### Options en ligne de commande
```bash
# Vérifier la détection de l'environnement et des outils disponibles
python3 run.py --diagnostics

# Ouvrir directement la fenêtre des paramètres et gestion des modules
python3 run.py --settings
```

### Installation globale en mode éditable
```bash
pip install -e .
vorssaint
```

---

## 🧩 Comment ajouter un nouveau module

Tous les modules résident dans `vorssaint/modules/<nom_du_module>/` et héritent de `BaseModule`.

Exemple d'un module minimal :

```python
# vorssaint/modules/mon_outil/module.py
from vorssaint.core.module import BaseModule
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu

class MonOutilModule(BaseModule):
    @property
    def id(self) -> str:
        return "mon_outil"

    @property
    def name(self) -> str:
        return "Mon Outil"

    @property
    def description(self) -> str:
        return "Description de mon outil utile."

    @property
    def category(self) -> str:
        return "system"  # 'energy', 'clipboard', 'audio', 'system'

    def on_enable(self) -> None:
        # Initialiser les ressources (timers, hooks, processus...)
        pass

    def on_disable(self) -> None:
        # Libérer impérativement toutes les ressources
        pass

    def get_tray_actions(self, parent_menu: QMenu) -> list:
        # Retourne les actions affichées dans le menu tray
        action = QAction("Action de Mon Outil", parent_menu)
        action.triggered.connect(self._do_something)
        return [action]

    def _do_something(self):
        self.app.env.send_notification("Mon Outil", "Action exécutée avec succès !")
```

Le `ModuleManager` découvre et charge automatiquement le nouveau module au démarrage de l'application !

---

## 🧪 Tests Unitaires

Lancer la suite de tests automatisés :
```bash
python3 -m unittest discover tests
```

---

## 🔒 Confidentialité & Local-First

- **Zéro télémétrie** : Aucune requête réseau sortante vers des serveurs externes.
- **Données 100% locales** : Tout l'historique et les notes restent confinés dans votre répertoire utilisateur (`~/.config/vorssaint` et `~/.local/share/vorssaint`).
- **Filtrage des données sensibles** : L'historique du presse-papiers ignore automatiquement les motifs de clés privées SSH, tokens GitHub/GitLab et JWT.

---

## 📄 Licence
Licence MIT - Libre d'utilisation, de modification et de distribution.
