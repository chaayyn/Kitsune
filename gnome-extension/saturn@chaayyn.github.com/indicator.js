// Bouton Saturn dans la barre du haut et son menu ancré.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

import {ClipboardBridge} from './clipboard.js';
import {DaemonClient, openClipboard, openScratchpad, openSettings} from './daemon.js';

const CATEGORIES = [
    ['clipboard', 'Presse-papiers'],
    ['tools', 'Outils'],
    ['system', 'Système'],
    ['sound', 'Son'],
    ['windows', 'Fenêtres'],
    ['energy', 'Énergie'],
    ['capture', 'Capture'],
];

const STATUS_LABELS = {
    running: 'Actif',
    off: 'Désactivé',
    starting: 'Démarrage',
    error: 'Erreur',
    unavailable: 'Indisponible',
};

/** Même règle que l'interface Qt (saturn/ui/models.py). */
export function moduleStatus(module) {
    if (module.enabled) {
        if (module.running)
            return 'running';
        if (!module.available)
            return 'unavailable';
        return module.error ? 'error' : 'starting';
    }
    return module.available ? 'off' : 'unavailable';
}

function categoryLabel(category) {
    return CATEGORIES.find(([key]) => key === category)?.[1] ??
        (category ? category[0].toUpperCase() + category.slice(1) : 'Autres');
}

function categoryRank(category) {
    const index = CATEGORIES.findIndex(([key]) => key === category);
    return index < 0 ? CATEGORIES.length : index;
}

// St calcule la largeur sans l'espacement des lettres : sans ceci, les libellés
// mono espacés seraient coupés par des « … ».
function noEllipsis(actor) {
    actor.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
    return actor;
}

function label(text, styleClass, params = {}) {
    return noEllipsis(new St.Label({text, style_class: styleClass, y_align: Clutter.ActorAlign.CENTER, ...params}));
}

/** Point coloré + libellé mono. */
const StatusPill = GObject.registerClass(
class StatusPill extends St.BoxLayout {
    _init() {
        super._init({style_class: 'saturn-status', y_align: Clutter.ActorAlign.CENTER});
        this._dot = new St.Widget({style_class: 'saturn-dot', y_align: Clutter.ActorAlign.CENTER});
        this._label = label('', 'saturn-status-label');
        this.add_child(this._dot);
        this.add_child(this._label);
    }

    set(status, text = STATUS_LABELS[status] ?? status) {
        for (const name of Object.keys(STATUS_LABELS))
            this.remove_style_class_name(`saturn-status-${name}`);
        this.add_style_class_name(`saturn-status-${status}`);
        this._label.text = text.toUpperCase();
    }
});

/** Ligne d'un module : nom, description, état et interrupteur. */
const ModuleItem = GObject.registerClass(
class ModuleItem extends PopupMenu.PopupBaseMenuItem {
    _init(module, onToggle) {
        super._init({style_class: 'saturn-module'});
        this._onToggle = onToggle;
        this._syncing = false;

        const text = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            x_expand: true,
            style_class: 'saturn-module-text',
        });
        this._name = label('', 'saturn-module-name');
        this._description = label('', 'saturn-module-description');
        this._description.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        this._status = new StatusPill();
        text.add_child(this._name);
        text.add_child(this._description);
        text.add_child(this._status);
        this.add_child(text);

        this._switch = new PopupMenu.Switch(false);
        this._switch.add_style_class_name('saturn-switch');
        this._switch.connect('notify::state', () => {
            if (!this._syncing)
                this._onToggle(this.moduleId, this._switch.state);
        });
        this.add_child(this._switch);

        this.update(module);
    }

    update(module) {
        this.moduleId = module.id;
        this.module = module;
        const status = moduleStatus(module);
        this._name.text = module.name;
        this._description.text = status === 'error' && module.error ? module.error : module.description;
        this._status.set(status);
        this.setPending(false);
        this._syncing = true;
        this._switch.state = Boolean(module.enabled);
        this._syncing = false;
        this._switch.reactive = module.available || module.enabled;
        this.accessible_name = `${module.name} : ${STATUS_LABELS[status] ?? status}`;
    }

    setPending(pending) {
        if (pending) {
            this.add_style_pseudo_class('insensitive');
            this._status.set('starting', '…');
        } else {
            this.remove_style_pseudo_class('insensitive');
        }
    }

    revert() {
        this.update(this.module);
    }

    // Cliquer sur la ligne bascule l'interrupteur sans fermer le menu.
    activate(_event) {
        if (this._switch.reactive)
            this._switch.toggle();
    }
});

function makeButton(text, primary, onClicked) {
    // Libellé fourni par nous (et non `label:`) pour maîtriser sa largeur.
    const buttonLabel = label(text.toUpperCase(), 'saturn-button-label');
    const button = new St.Button({
        child: buttonLabel,
        style_class: primary ? 'saturn-button saturn-button-primary' : 'saturn-button',
        can_focus: true,
        y_align: Clutter.ActorAlign.CENTER,
        accessible_name: text,
    });
    button.setText = value => {
        buttonLabel.text = value.toUpperCase();
    };
    button.connect('clicked', onClicked);
    return button;
}

export const SaturnIndicator = GObject.registerClass(
class SaturnIndicator extends PanelMenu.Button {
    _init(extension) {
        super._init(0.5, 'Saturn');
        this._extension = extension;
        this._items = new Map();
        this._version = '';
        this._environment = {};
        this._startTried = false;

        const iconFile = Gio.File.new_for_path(`${extension.path}/icons/saturn-symbolic.svg`);
        this._icon = new St.Icon({
            gicon: new Gio.FileIcon({file: iconFile}),
            style_class: 'system-status-icon saturn-panel-icon',
        });
        this.add_child(this._icon);

        this.menu.actor.add_style_class_name('saturn-menu');
        this._buildMenu();

        this._clipboard = new ClipboardBridge();
        this._client = new DaemonClient({
            onAvailableChanged: available => this._onAvailableChanged(available),
            onModuleChanged: (id, module) => this._upsert(module),
        });
        this._sync();

        // À l'activation de l'extension, saturnd est démarré s'il est activable.
        this._autoStartId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 2, () => {
            this._autoStartId = 0;
            if (!this._client.available)
                this._client.isActivatable()
                    .then(activatable => activatable && this._startDaemon(false))
                    .catch(logError);
            return GLib.SOURCE_REMOVE;
        });

        this.menu.connect('open-state-changed', (_menu, open) => {
            if (open && this._client.available)
                this._refresh();
        });
    }

    // -- construction -----------------------------------------------------------

    _buildMenu() {
        // En-tête : titre, état du démon, version / bureau.
        const header = new PopupMenu.PopupBaseMenuItem({
            reactive: false, can_focus: false, style_class: 'saturn-header',
        });
        const headerBox = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL, x_expand: true});
        const titleRow = new St.BoxLayout({x_expand: true});
        titleRow.add_child(label('Saturn', 'saturn-title', {x_expand: true}));
        this._daemonStatus = new StatusPill();
        titleRow.add_child(this._daemonStatus);
        headerBox.add_child(titleRow);
        this._meta = label('', 'saturn-meta');
        headerBox.add_child(this._meta);
        header.add_child(headerBox);
        this.menu.addMenuItem(header);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Liste des modules.
        this._modulesSection = new PopupMenu.PopupMenuSection();
        this.menu.addMenuItem(this._modulesSection);

        // État hors ligne.
        this._offline = new PopupMenu.PopupBaseMenuItem({
            reactive: false, can_focus: false, style_class: 'saturn-offline',
        });
        const offlineBox = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL, x_expand: true});
        offlineBox.add_child(label('HORS LIGNE', 'saturn-eyebrow saturn-eyebrow-danger'));
        offlineBox.add_child(label('Le démon\nn\'est pas lancé.', 'saturn-offline-title'));
        const hint = label('Saturn a besoin de saturnd pour faire tourner ses modules.', 'saturn-offline-hint');
        hint.clutter_text.line_wrap = true;
        offlineBox.add_child(hint);
        this._startButton = makeButton('Démarrer saturnd', true, () => this._startDaemon(true));
        this._startButton.x_align = Clutter.ActorAlign.START;
        offlineBox.add_child(this._startButton);
        this._offline.add_child(offlineBox);
        this.menu.addMenuItem(this._offline);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Pied : compteur et accès aux réglages.
        const footer = new PopupMenu.PopupBaseMenuItem({
            reactive: false, can_focus: false, style_class: 'saturn-footer',
        });
        this._counter = label('—', 'saturn-counter', {x_expand: true});
        footer.add_child(this._counter);
        this._historyButton = makeButton('Historique', false, () => {
            this.menu.close();
            openClipboard().catch(error => Main.notifyError('Saturn', error.message));
        });
        footer.add_child(this._historyButton);
        this._notesButton = makeButton('Notes', false, () => {
            this.menu.close();
            openScratchpad().catch(error => Main.notifyError('Saturn', error.message));
        });
        footer.add_child(this._notesButton);
        footer.add_child(makeButton('Réglages ↗', true, () => {
            this.menu.close();
            openSettings().catch(error => Main.notifyError('Saturn', error.message));
        }));
        this.menu.addMenuItem(footer);
    }

    // -- état -------------------------------------------------------------------

    _onAvailableChanged(available) {
        if (available) {
            this._startButton.reactive = true;
            this._refresh();
        } else {
            this._modulesSection.removeAll();
            this._items.clear();
        }
        this._sync();
    }

    async _refresh() {
        try {
            const [modules, environment, version] = await Promise.all([
                this._client.listModules(),
                this._client.getEnvironment(),
                this._client.getVersion(),
            ]);
            this._environment = environment;
            this._version = version;
            this._rebuild(modules);
        } catch (error) {
            logError(error, 'Saturn : lecture des modules impossible');
        }
        this._sync();
    }

    _rebuild(modules) {
        this._modulesSection.removeAll();
        this._items.clear();
        const sorted = [...modules].sort((a, b) =>
            categoryRank(a.category) - categoryRank(b.category) || a.name.localeCompare(b.name));

        let currentCategory = null;
        for (const module of sorted) {
            if (module.category !== currentCategory) {
                currentCategory = module.category;
                const section = new PopupMenu.PopupBaseMenuItem({
                    reactive: false, can_focus: false, style_class: 'saturn-section',
                });
                section.add_child(label(categoryLabel(currentCategory).toUpperCase(), 'saturn-eyebrow'));
                this._modulesSection.addMenuItem(section);
            }
            const item = new ModuleItem(module, (id, enabled) => this._toggle(id, enabled));
            this._items.set(module.id, item);
            this._modulesSection.addMenuItem(item);
        }
    }

    _upsert(module) {
        const item = this._items.get(module.id);
        if (item)
            item.update(module);
        else
            this._refresh();
        this._sync();
    }

    async _toggle(id, enabled) {
        const item = this._items.get(id);
        item?.setPending(true);
        try {
            this._upsert(await this._client.setModuleEnabled(id, enabled));
        } catch (error) {
            item?.revert();
            Main.notifyError('Saturn', error.message);
        }
    }

    async _startDaemon(userAsked) {
        if (this._client.available || this._startTried && !userAsked)
            return;
        this._startTried = true;
        this._startButton.reactive = false;
        this._startButton.setText('Démarrage…');
        try {
            await this._client.start();
        } catch (error) {
            if (userAsked)
                Main.notifyError('Saturn', `Impossible de lancer saturnd : ${error.message}`);
        } finally {
            this._startButton.reactive = true;
            this._startButton.setText('Démarrer saturnd');
        }
    }

    _sync() {
        const online = this._client?.available ?? false;
        this._daemonStatus.set(online ? 'running' : 'error', online ? 'En ligne' : 'Hors ligne');
        this._offline.visible = !online;
        this._modulesSection.actor.visible = online;
        this._meta.text = online
            ? [`v${this._version}`, this._environment.desktop, this._environment.session]
                .filter(part => part && part.length > 1).join('  ·  ').toUpperCase()
            : 'SATURND NE RÉPOND PAS';

        const modules = [...this._items.values()].map(item => item.module);
        const active = modules.filter(module => moduleStatus(module) === 'running').length;
        this._counter.text = online ? `${active} / ${modules.length} ACTIFS` : '—';
        this._icon.opacity = online ? 255 : 140;

        // Le presse-papiers ne passe par l'extension que sous Wayland (sous X11, saturnd le lit lui-même).
        const clipboard = this._items.get('clipboard')?.module;
        const clipboardOn = online && clipboard !== undefined && moduleStatus(clipboard) === 'running';
        this._historyButton.visible = clipboardOn;
        const notes = this._items.get('scratchpad')?.module;
        this._notesButton.visible = online && notes !== undefined && moduleStatus(notes) === 'running';
        this._clipboard?.setActive(clipboardOn && this._environment.session === 'wayland');
    }

    destroy() {
        if (this._autoStartId) {
            GLib.source_remove(this._autoStartId);
            this._autoStartId = 0;
        }
        this._clipboard?.destroy();
        this._clipboard = null;
        this._client?.destroy();
        this._client = null;
        super.destroy();
    }
});
