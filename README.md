# Saturn

Boîte à outils modulaire et *local-first* pour les bureaux Linux (GNOME, KDE, Hyprland, Sway…, sous Wayland comme sous X11). Chaque fonction est un module que l'on active ou désactive ; un module désactivé n'est même pas chargé.

> État : étape 3. Le démon, le système de modules, l'API D-Bus, un premier module (Clean URL), l'interface Qt/QML et l'extension GNOME Shell fonctionnent.

## Architecture

```
saturnd (Python, asyncio sur la boucle GLib)
├── ModuleManager   active/désactive les modules, applique les réglages
├── Registry        lit le MANIFEST de chaque module sans importer son code
├── Config          ~/.config/saturn/config.json (écriture atomique)
├── desktop.detect  bureau (gnome / kde / wlroots / other) + session (wayland / x11)
└── DBusService     org.saturn.Daemon sur le bus de session

saturn (interface PySide6 + QML, aucune logique métier)
├── DaemonClient    appels et signaux D-Bus via Gio
├── Backend         pont exposé au QML (« Saturn ») + modèles Qt
├── Theme           couleurs, polices, durées (« Theme »)
└── qml/            icône, panneau flottant, fenêtre de réglages

gnome-extension/saturn@chaayyn.github.com (GNOME Shell 50+, GJS)
├── extension.js    bouton dans la barre du haut, nom org.saturn.Shell
├── indicator.js    menu ancré : modules, interrupteurs, état du démon
└── daemon.js       client D-Bus de saturnd, ouverture des réglages Qt
```

Données : `~/.config/saturn/` pour les réglages, `~/.local/share/saturn/modules/<id>.db` pour les bases SQLite des modules (créées seulement à la première utilisation).

## Installer

```bash
./scripts/install.sh      # désinstaller : ./scripts/uninstall.sh
```

Sans `sudo`, pour l'utilisateur courant : lanceurs `saturnd` et `saturn` dans `~/.local/bin` (ils pointent vers ce dépôt), activation D-Bus de `org.saturn.Daemon` (le démon démarre à la première demande), police Space Grotesk et extension GNOME Shell. Sous GNOME Wayland, l'extension n'est chargée qu'après une déconnexion / reconnexion.

## Lancer

Dépendances système (Debian / Kali) : `python3-gi` (PyGObject) et `dbus`.

```bash
python3 -m saturn --verbose        # ou `saturnd` après `pip install -e .`
```

`--replace` remplace une instance déjà lancée ; sinon une deuxième instance refuse de démarrer.

## Interface

Dépendances : `python3-pyside6.qtquick` et les modules QML Qt 6.

```bash
sudo apt install python3-pyside6.qtquick qml6-module-qtquick qml6-module-qtquick-controls \
  qml6-module-qtquick-layouts qml6-module-qtquick-window qml6-module-qtquick-templates \
  qml6-module-qtqml-workerscript fonts-jetbrains-mono
python3 -m saturn.ui               # ou `saturn` après `pip install -e .`
```

- **Icône** dans la zone de notification (StatusNotifierItem), pour KDE, Hyprland, Sway… Sous GNOME, l'extension de Saturn la remplace : l'icône Qt se masque toute seule tant que l'extension tourne (nom D-Bus `org.saturn.Shell`).
- **Panneau** (clic sur l'icône) : modules par catégorie, état et interrupteur. Il se ferme quand il perd le focus ou avec Échap. Sous Wayland, c'est le compositeur qui le place (souvent au centre) : une appli ne peut pas se positionner elle-même.
- **Réglages** : liste des modules à gauche, détail et réglages générés à partir du schéma du démon à droite. Tout se met à jour en direct par les signaux D-Bus.
- **Démon arrêté** : l'interface l'indique et propose de lancer `saturnd` (journal dans `~/.local/state/saturn/saturnd.log`).
- **Une seule instance** : relancer `saturn` ouvre le panneau de l'instance existante (`--panel`, `--settings [module]`).
- **Polices** : Space Grotesk (titres, livrée dans `assets/fonts/` sous licence OFL) et JetBrains Mono (valeurs, paquet `fonts-jetbrains-mono`). Sans elles, repli sur Adwaita Sans / Fira Code ; `SATURN_DISPLAY_FONT` et `SATURN_MONO_FONT` imposent une autre famille installée.
- **Animations** : expo-out, 200 à 450 ms, coupées si GNOME a désactivé les animations ou si `SATURN_REDUCED_MOTION=1`.

## Extension GNOME Shell

Un bouton Saturn dans la barre du haut, avec un menu ancré dessous : modules par catégorie, état et interrupteur (cliquer sur la ligne bascule le module sans fermer le menu), état du démon et bouton « Réglages » qui ouvre la fenêtre Qt. À l'activation, l'extension démarre `saturnd` par activation D-Bus s'il ne tourne pas ; sinon le menu propose de le lancer.

Elle ne fait que relayer l'API D-Bus du démon : aucune logique métier côté Shell. Pour la tester sans toucher à sa session, on peut lancer un GNOME Shell isolé : `dbus-run-session gnome-shell --headless --wayland --virtual-monitor 1280x800`, avec `XDG_DATA_HOME` / `XDG_CONFIG_HOME` temporaires.

L'interface parle au démon avec Gio plutôt que QtDBus : PySide6 convertit mal les `a{sv}` de l'API, et la boucle Qt sous Linux est une boucle GLib, donc les rappels Gio y sont traités directement.

## API D-Bus

Nom `org.saturn.Daemon`, objet `/org/saturn/Daemon`, interface `org.saturn.Daemon1`.

| Méthode | Rôle |
|---|---|
| `ListModules() → aa{sv}` | tous les modules : `id`, `name`, `description`, `category`, `enabled`, `running`, `available`, `missing`, `error`, `actions` |
| `GetModule(s) → a{sv}` | un module |
| `SetModuleEnabled(s, b) → a{sv}` | activer / désactiver (persisté) |
| `GetSettingsSchema(s) → aa{sv}` | description typée des réglages |
| `GetSettings(s) → a{sv}` / `SetSetting(s, s, v)` / `ResetSetting(s, s)` | réglages |
| `CallAction(s, s, a{sv}) → a{sv}` | action propre à un module |
| `GetEnvironment() → a{sv}` | bureau et session détectés |

Propriété `Version`. Signaux : `ModuleStateChanged(s, a{sv})`, `SettingChanged(s, s, v)`, `ModuleEvent(s, s, a{sv})`. Les erreurs ont des noms `org.saturn.Error.*`.

```bash
D() { gdbus call --session -d org.saturn.Daemon -o /org/saturn/Daemon -m org.saturn.Daemon1.$1 "${@:2}"; }
D ListModules
D SetModuleEnabled clean_url false
D CallAction clean_url clean "{'url': <'https://youtu.be/abc?si=xyz'>}"
D SetSetting clean_url extra_params "<['ref_*']>"
```

## Écrire un module

Un module est un sous-paquet de `saturn/modules/` :

- `__init__.py` ne contient que le `MANIFEST` (`ModuleInfo` : id, nom, catégorie, réglages, dépendances système). Il est lu même quand le module est désactivé, donc pas d'import lourd ici.
- l'implémentation (par ex. `module.py`) hérite de `saturn.module.Module`. Elle est importée seulement à l'activation : `start()` / `stop()` pour les ressources, `on_setting_changed()`, et des méthodes marquées `@action()` appelables par D-Bus.

Le contexte `self.ctx` donne les réglages, l'environnement détecté (`ctx.env`), une base SQLite paresseuse (`ctx.database()`) et `ctx.emit()` pour pousser des évènements. `saturn/modules/clean_url/` sert d'exemple.

## Tests

```bash
python3 -m pytest
```

Les tests D-Bus lancent un vrai `saturnd` sur un bus privé (`dbus-daemon` requis) et n'écrivent jamais dans votre `~/.config`. Les tests de l'interface tournent hors écran (`QT_QPA_PLATFORM=offscreen`).

## Licence

GPL-3.0-or-later.
