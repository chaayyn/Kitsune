# Saturn

Boîte à outils modulaire et *local-first* pour les bureaux Linux (GNOME, KDE, Hyprland, Sway…, sous Wayland comme sous X11). Chaque fonction est un module que l'on active ou désactive ; un module désactivé n'est même pas chargé.

> État : étape 7. Le démon, le système de modules, l'API D-Bus, l'interface Qt/QML, l'extension GNOME Shell et cinq modules (Clean URL, Presse-papiers, Bloc-notes, Rester éveillé, Mode nettoyage) fonctionnent.

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
├── awake.js        « Rester éveillé » en tête du menu : interrupteur et durées
├── cleaning.js     voile du mode nettoyage (prise modale du Shell)
├── clipboard.js    relais du presse-papiers sous GNOME Wayland
└── daemon.js       client D-Bus de saturnd, ouverture des fenêtres Qt
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
sudo apt install libxcb-cursor0   # sessions X11 seulement : requis par Qt 6.5+ pour xcb
python3 -m saturn.ui               # ou `saturn` après `pip install -e .`
```

- **Icône** dans la zone de notification (StatusNotifierItem), pour KDE, Hyprland, Sway… Sous GNOME, l'extension de Saturn la remplace : l'icône Qt se masque toute seule tant que l'extension tourne (nom D-Bus `org.saturn.Shell`).
- **Panneau** (clic sur l'icône) : modules par catégorie, état et interrupteur. Il se ferme quand il perd le focus ou avec Échap. Sous Wayland, c'est le compositeur qui le place (souvent au centre) : une appli ne peut pas se positionner elle-même.
- **Réglages** : liste des modules à gauche, détail et réglages générés à partir du schéma du démon à droite. Tout se met à jour en direct par les signaux D-Bus.
- **Démon arrêté** : l'interface l'indique et propose de lancer `saturnd` (journal dans `~/.local/state/saturn/saturnd.log`).
- **Une seule instance** : relancer `saturn` ouvre le panneau de l'instance existante (`--panel`, `--settings [module]`, `--clipboard`, `--scratchpad`, `--clean`).
- **Polices** : Space Grotesk (titres, livrée dans `assets/fonts/` sous licence OFL) et JetBrains Mono (valeurs, paquet `fonts-jetbrains-mono`). Sans elles, repli sur Adwaita Sans / Fira Code ; `SATURN_DISPLAY_FONT` et `SATURN_MONO_FONT` imposent une autre famille installée.
- **Animations** : expo-out, 200 à 450 ms, coupées si GNOME a désactivé les animations ou si `SATURN_REDUCED_MOTION=1`.

## Extension GNOME Shell

Un bouton Saturn dans la barre du haut, avec un menu ancré dessous : modules par catégorie, état et interrupteur (cliquer sur la ligne bascule le module sans fermer le menu), état du démon et bouton « Réglages » qui ouvre la fenêtre Qt. À l'activation, l'extension démarre `saturnd` par activation D-Bus s'il ne tourne pas ; sinon le menu propose de le lancer.

Elle ne fait que relayer l'API D-Bus du démon : aucune logique métier côté Shell. Pour la tester sans toucher à sa session, on peut lancer un GNOME Shell isolé : `dbus-run-session gnome-shell --headless --wayland --virtual-monitor 1280x800`, avec `XDG_DATA_HOME` / `XDG_CONFIG_HOME` temporaires.

L'interface parle au démon avec Gio plutôt que QtDBus : PySide6 convertit mal les `a{sv}` de l'API, et la boucle Qt sous Linux est une boucle GLib, donc les rappels Gio y sont traités directement.

## Modules

### Clean URL

Retire les paramètres de pistage des liens (`utm_*`, `fbclid`, `gclid`, `si`…), avec des listes de paramètres à retirer en plus ou à toujours garder. Action `clean`.

### Presse-papiers

Historique local du presse-papiers : texte, images et fichiers copiés, avec recherche, favoris, aperçu et recopie. Désactivé par défaut.

- **Fenêtre d'historique** : `Super+Maj+V` sous GNOME (raccourci de l'extension), sinon `saturn --clipboard` à lier à un raccourci de son bureau, ou le menu de l'icône. Saisir pour chercher, `↑↓` pour naviguer, `Entrée` pour recopier, `Ctrl+P` pour épingler, `Ctrl+Suppr` pour supprimer.
- **Secrets ignorés** : contenus marqués par un gestionnaire de mots de passe (KeePassXC…), clés privées, jetons GitHub / GitLab / Slack, clés AWS, Google, Stripe, clés d'API `sk-…`, JWT.
- **Réglages** : nombre d'éléments et durée de conservation (les favoris ne sont jamais supprimés), images et fichiers on/off, nettoyage automatique des liens copiés (via Clean URL), vidage du presse-papiers après un délai.
- **Selon le bureau** : sous GNOME Wayland, seule l'extension peut lire le presse-papiers, elle relaie donc les copies au démon. Sous KDE, Hyprland, Sway… c'est `wl-paste` / `wl-copy` (paquet `wl-clipboard`). Sous X11, c'est Gtk 3.
- **Stockage** : `~/.local/share/saturn/modules/clipboard.db` et les images dans `~/.local/share/saturn/modules/clipboard/images/`, lisibles par vous seul.

Actions : `push`, `list`, `get`, `copy`, `pin`, `delete`, `clear`. Évènements : `history-changed`, `ignored`, `link-cleaned`, `write` (écriture demandée à l'extension GNOME).

### Bloc-notes

Notes rapides en onglets, enregistrées au fil de la frappe (dans `~/.local/share/saturn/modules/scratchpad.db`). Le titre d'un onglet est la première ligne de la note.

- **Ouvrir** : `Super+Maj+N` sous GNOME, le bouton « Notes » du menu, `saturn --scratchpad` ou le menu de l'icône.
- **Éditer, Aperçu, Les deux** : l'aperçu met en forme le Markdown. `Ctrl+N` nouvelle note, `Ctrl+E` bascule l'aperçu, `Ctrl+Tab` note suivante. Supprimer un onglet demande une confirmation (deux clics sur ×).
- **Exporter** écrit la note en `.md` dans `~/Documents/Saturn` (réglable), sans jamais écraser un fichier existant.
- Plusieurs fenêtres ou clients restent synchronisés : chaque modification est diffusée (`notes-changed`).

Actions : `list`, `get`, `create`, `save`, `delete`, `move`, `export`. Réglages : dossier d'export, taille du texte.

### Rester éveillé

Empêche la mise en veille pour 15 min, 30 min, 1 h, 2 h, 5 h ou jusqu'à nouvel ordre. Actif par défaut, mais rien n'est bloqué tant qu'on ne lance pas le mode.

- **Où** : en tête du panneau Qt et du menu GNOME (grand bouton, durées, compte à rebours), et dans le menu de l'icône. Sous GNOME, l'icône de la barre passe au doré tant que le mode est actif.
- **Comment, selon le bureau** : gestionnaire de session GNOME, sinon portail XDG (KDE, Hyprland…), sinon `org.freedesktop.ScreenSaver` pour l'écran ; ce qui reste (et le capot) passe par systemd-logind. Les inhibitions sont liées à la connexion D-Bus de `saturnd` : s'il s'arrête, même brutalement, la veille redevient normale.
- **Réglages** : durée par défaut, garder l'écran allumé (sinon seule la veille est bloquée), ignorer la fermeture du capot, arrêt sous un seuil de batterie (UPower, 10 % par défaut), activation au démarrage de `saturnd`.
- La fin de session suit l'horloge murale : après une mise en veille forcée, l'heure de fin reste juste. Quand le démon arrête le mode (durée écoulée, batterie), l'interface et GNOME affichent une notification.

Actions : `start` (`minutes`, 0 = sans fin ; sinon la durée par défaut), `stop`, `toggle`, `status`. Évènement : `state-changed` (avec `reason` : `user`, `timer`, `battery`, `settings`, `error`).

### Mode nettoyage

Un voile noir plein écran qui bloque le clavier, le temps d'essuyer l'écran et les touches. Actif par défaut.

- **Lancer** : ligne « Mode nettoyage » du menu GNOME ou du panneau, menu de l'icône, ou `saturn --clean` (à lier à un raccourci de son bureau).
- **Sortir** : maintenir le bouton 1,5 s, ou attendre la fin du délai (60 s par défaut, de 10 à 600). Avec « Bloquer aussi la souris », seule la fin du délai fait sortir.
- **Ce qui est bloqué, selon le bureau** : sous GNOME, l'extension pose le voile avec une prise modale du Shell : touches, raccourcis du bureau et clics n'atteignent plus rien. Sous X11, l'interface Qt capture clavier et souris. Sous KDE, Hyprland ou Sway (Wayland), la fenêtre plein écran reçoit les touches, mais les raccourcis du compositeur restent actifs.
- **Sécurité** : le démon tient l'horloge ; si `saturnd` disparaît, le voile tombe aussitôt, et il tombe de toute façon 5 s après la fin annoncée. Pendant le nettoyage, l'écran ne s'éteint pas.

Actions : `start` (`seconds`, sinon la durée réglée), `stop`, `status`. Évènement : `state-changed` (`surface` : `shell` ou `ui`, selon qui affiche le voile).

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

Le contexte `self.ctx` donne les réglages, l'environnement détecté (`ctx.env`), une base SQLite paresseuse (`ctx.database()`), `ctx.emit()` pour pousser des évènements, `ctx.set_notice()` pour afficher un avertissement sous le module, et `ctx.call_module()` pour appeler l'action d'un autre module. Une dépendance peut être limitée à un bureau : `Requirement.binary("wl-paste", sessions=("wayland",), families=("kde", "wlroots"))`. `saturn/modules/clean_url/` sert d'exemple.

## Tests

```bash
python3 -m pytest
```

Les tests D-Bus lancent un vrai `saturnd` sur un bus privé (`dbus-daemon` requis) et n'écrivent jamais dans votre `~/.config`. Ce bus sert aussi de bus système : « Rester éveillé » y parle à de faux GNOME, portail, logind et UPower (`tests/fake_power_services.py`), jamais aux vrais. Les tests de l'interface tournent hors écran (`QT_QPA_PLATFORM=offscreen`).

## Licence

GPL-3.0-or-later.
