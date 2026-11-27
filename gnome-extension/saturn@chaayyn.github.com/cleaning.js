// Mode nettoyage côté GNOME : voile noir sur tous les écrans, avec une prise
// modale du Shell. Clavier, raccourcis et (au besoin) souris n'atteignent plus
// rien. On sort en maintenant le bouton, ou à la fin du délai fixé par saturnd.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Pango from 'gi://Pango';
import Shell from 'gi://Shell';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';

export const MODULE_ID = 'cleaning';

/** Temps d'appui pour sortir, en millisecondes. */
export const HOLD_MS = 1500;

/** Marge après la fin annoncée : si le démon ne dit rien, le voile tombe quand même. */
const SAFETY_MS = 5000;

function text(value, styleClass) {
    const label = new St.Label({text: value, style_class: styleClass});
    label.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
    return label;
}

function countdown(seconds) {
    const total = Math.max(0, Math.ceil(seconds));
    const minutes = Math.floor(total / 60);
    const rest = total % 60;
    return `${minutes}:${rest < 10 ? '0' : ''}${rest}`;
}

export class CleaningOverlay {
    /** @param {() => void} onExit appelé quand l'utilisateur a maintenu le bouton */
    constructor(onExit) {
        this._onExit = onExit;
        this._actor = null;
        this._grab = null;
        this._tickId = 0;
        this._holdId = 0;
        this._safetyId = 0;
    }

    get visible() {
        return this._actor !== null;
    }

    /** Affiche (ou met à jour) le voile pour l'état reçu du démon. */
    show(state) {
        this._until = Number(state.until ?? 0);
        this._seconds = Math.max(1, Number(state.seconds ?? 60));
        this._blockPointer = Boolean(state.block_pointer);
        if (!this._actor)
            this._build();
        this._exit.visible = !this._blockPointer;
        this._hint.text = this._blockPointer
            ? 'CLAVIER ET SOURIS BLOQUÉS  ·  SORTIE À LA FIN DU DÉLAI'
            : 'CLAVIER BLOQUÉ  ·  MAINTENEZ LE BOUTON POUR SORTIR';
        this._tick();
        this._armSafety();
    }

    hide() {
        if (!this._actor)
            return;
        this._clearTimers();
        if (this._grab) {
            Main.popModal(this._grab);
            this._grab = null;
        }
        const actor = this._actor;
        this._actor = null;
        actor.remove_all_transitions();
        actor.ease({
            opacity: 0,
            duration: 320,
            mode: Clutter.AnimationMode.EASE_OUT_EXPO,
            onComplete: () => actor.destroy(),
        });
    }

    destroy() {
        this.hide();
        this._onExit = null;
    }

    // -- construction -------------------------------------------------------------

    _build() {
        this._actor = new St.Widget({
            style_class: 'saturn-cleaning',
            reactive: true,
            can_focus: true,
            opacity: 0,
            x: 0,
            y: 0,
            width: global.stage.width,
            height: global.stage.height,
            layout_manager: new Clutter.FixedLayout(),
        });
        // Toute touche s'arrête ici : rien ne passe au bureau ni aux fenêtres.
        this._actor.connect('key-press-event', () => Clutter.EVENT_STOP);
        this._actor.connect('key-release-event', () => Clutter.EVENT_STOP);

        const monitor = Main.layoutManager.primaryMonitor;
        const content = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            style_class: 'saturn-cleaning-content',
            x: monitor.x,
            y: monitor.y,
            width: monitor.width,
            height: monitor.height,
        });

        const center = new St.BoxLayout({
            orientation: Clutter.Orientation.VERTICAL,
            x_align: Clutter.ActorAlign.CENTER,
            y_align: Clutter.ActorAlign.CENTER,
            x_expand: true,
            y_expand: true,
        });
        center.add_child(text('SATURN  ·  MODE NETTOYAGE', 'saturn-cleaning-eyebrow'));
        center.add_child(text('Nettoyez.', 'saturn-cleaning-title'));
        this._hint = text('', 'saturn-cleaning-hint');
        center.add_child(this._hint);
        this._clock = text('', 'saturn-cleaning-clock');
        center.add_child(this._clock);

        // Bouton « maintenir pour sortir » : un remplissage avance tant qu'on appuie.
        this._exit = new St.Widget({
            style_class: 'saturn-cleaning-exit',
            reactive: true,
            track_hover: true,
            x_align: Clutter.ActorAlign.START,
            layout_manager: new Clutter.BinLayout(),
        });
        // Une piste horizontale garde le remplissage collé à gauche.
        const track = new St.BoxLayout({x_expand: true, y_expand: true});
        this._fill = new St.Widget({style_class: 'saturn-cleaning-fill', y_expand: true});
        this._fill.width = 0;
        track.add_child(this._fill);
        this._exit.add_child(track);
        this._exitLabel = text('MAINTENIR POUR SORTIR', 'saturn-cleaning-exit-label');
        this._exitLabel.x_align = Clutter.ActorAlign.CENTER;
        this._exitLabel.y_align = Clutter.ActorAlign.CENTER;
        this._exit.add_child(this._exitLabel);
        this._exit.connect('button-press-event', () => this._startHold());
        this._exit.connect('button-release-event', () => this._cancelHold());
        this._exit.connect('leave-event', () => this._cancelHold());
        this._exit.connect('touch-event', (_actor, event) => {
            const type = event.type();
            if (type === Clutter.EventType.TOUCH_BEGIN)
                this._startHold();
            else if (type === Clutter.EventType.TOUCH_END || type === Clutter.EventType.TOUCH_CANCEL)
                this._cancelHold();
            return Clutter.EVENT_STOP;
        });
        center.add_child(this._exit);
        content.add_child(center);

        // Temps restant : un trait de 1 px qui se rétracte en bas de l'écran.
        this._bar = new St.Widget({style_class: 'saturn-cleaning-bar'});
        content.add_child(this._bar);

        this._actor.add_child(content);
        Main.layoutManager.addTopChrome(this._actor);

        this._grab = Main.pushModal(this._actor, {actionMode: Shell.ActionMode.NONE});
        this._actor.grab_key_focus();
        this._actor.ease({opacity: 255, duration: 450, mode: Clutter.AnimationMode.EASE_OUT_EXPO});

        this._tickId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 250, () => {
            this._tick();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _tick() {
        if (!this._actor)
            return;
        const left = this._until - Date.now() / 1000;
        this._clock.text = countdown(left);
        const monitor = Main.layoutManager.primaryMonitor;
        this._bar.width = Math.round(monitor.width * Math.max(0, Math.min(1, left / this._seconds)));
    }

    _armSafety() {
        if (this._safetyId)
            GLib.source_remove(this._safetyId);
        const delay = Math.max(0, this._until * 1000 - Date.now()) + SAFETY_MS;
        this._safetyId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, delay, () => {
            this._safetyId = 0;
            this.hide();
            return GLib.SOURCE_REMOVE;
        });
    }

    _startHold() {
        if (this._holdId || this._blockPointer)
            return Clutter.EVENT_STOP;
        const started = GLib.get_monotonic_time();
        const width = this._exit.width;
        this._exit.add_style_pseudo_class('active');
        this._holdId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 16, () => {
            const progress = Math.min(1, (GLib.get_monotonic_time() - started) / 1000 / HOLD_MS);
            this._fill.width = Math.round(width * progress);
            if (progress < 1)
                return GLib.SOURCE_CONTINUE;
            this._holdId = 0;
            this._exitLabel.text = 'À BIENTÔT';
            this._onExit?.();
            return GLib.SOURCE_REMOVE;
        });
        return Clutter.EVENT_STOP;
    }

    _cancelHold() {
        if (this._holdId) {
            GLib.source_remove(this._holdId);
            this._holdId = 0;
        }
        if (this._exit) {
            this._exit.remove_style_pseudo_class('active');
            this._fill.ease({width: 0, duration: 320, mode: Clutter.AnimationMode.EASE_OUT_EXPO});
        }
        return Clutter.EVENT_STOP;
    }

    _clearTimers() {
        for (const id of [this._tickId, this._holdId, this._safetyId]) {
            if (id)
                GLib.source_remove(id);
        }
        this._tickId = this._holdId = this._safetyId = 0;
    }
}
