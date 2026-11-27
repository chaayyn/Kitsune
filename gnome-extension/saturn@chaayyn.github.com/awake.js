// « Rester éveillé » dans le menu : état, interrupteur et durées.
//
// L'état vient de saturnd (module keep_awake) ; ici on l'affiche et on relaie
// les clics. Le compte à rebours n'avance que lorsque le menu est ouvert.

import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import St from 'gi://St';

import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

export const MODULE_ID = 'keep_awake';

export const DURATIONS = [
    [0, '∞', 'Jusqu\'à nouvel ordre'],
    [15, '15 min', '15 minutes'],
    [30, '30 min', '30 minutes'],
    [60, '1 h', '1 heure'],
    [120, '2 h', '2 heures'],
    [300, '5 h', '5 heures'],
];

/** Messages quand le démon arrête le mode de lui-même (même texte que l'interface Qt). */
export const STOP_MESSAGES = {
    timer: 'Durée écoulée : la mise en veille est de nouveau permise.',
    battery: 'Batterie faible : « Rester éveillé » s\'est arrêté.',
    error: '« Rester éveillé » s\'est arrêté : plus aucun service ne bloque la veille.',
};

function pad(value) {
    return value < 10 ? `0${value}` : `${value}`;
}

/** « 1:05:09 » ou « 05:09 ». */
export function formatRemaining(seconds) {
    const total = Math.max(0, Math.round(seconds));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor(total % 3600 / 60);
    return `${hours > 0 ? `${hours}:` : ''}${pad(minutes)}:${pad(total % 60)}`;
}

function text(value, styleClass, params = {}) {
    const actor = new St.Label({text: value, style_class: styleClass, y_align: Clutter.ActorAlign.CENTER, ...params});
    actor.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
    return actor;
}

export const AwakeItem = GObject.registerClass(
class AwakeItem extends PopupMenu.PopupBaseMenuItem {
    /**
     * @param {object} handlers
     * @param {(minutes: number) => void} handlers.onStart
     * @param {() => void} handlers.onStop
     */
    _init({onStart, onStop}) {
        super._init({style_class: 'saturn-awake', activate: false});
        this._onStart = onStart;
        this._onStop = onStop;
        this._state = {};
        this._busy = false;
        this._tickId = 0;
        this._syncing = false;

        const column = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL, x_expand: true});

        const top = new St.BoxLayout({x_expand: true, style_class: 'saturn-awake-top'});
        const texts = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL, x_expand: true});
        this._eyebrow = text('RESTER ÉVEILLÉ', 'saturn-eyebrow');
        this._headline = text('', 'saturn-awake-headline');
        this._detail = text('', 'saturn-awake-detail');
        this._detail.clutter_text.ellipsize = Pango.EllipsizeMode.END;
        texts.add_child(this._eyebrow);
        texts.add_child(this._headline);
        texts.add_child(this._detail);
        top.add_child(texts);

        this._switch = new PopupMenu.Switch(false);
        this._switch.add_style_class_name('saturn-switch');
        this._switch.y_align = Clutter.ActorAlign.CENTER;
        this._switch.connect('notify::state', () => {
            if (!this._syncing)
                this._toggle();
        });
        top.add_child(this._switch);
        column.add_child(top);

        const chips = new St.BoxLayout({x_expand: true, style_class: 'saturn-chips'});
        this._chips = DURATIONS.map(([minutes, label, accessible]) => {
            const chipLabel = text(label, 'saturn-chip-label');
            const chip = new St.Button({
                child: chipLabel,
                style_class: minutes === 0 ? 'saturn-chip saturn-chip-infinite' : 'saturn-chip',
                x_expand: true,
                can_focus: true,
                accessible_name: accessible,
            });
            chip.connect('clicked', () => {
                if (this._busy)
                    return;
                if (this._isCurrent(minutes))
                    this._run(() => this._onStop());
                else
                    this._run(() => this._onStart(minutes));
            });
            chips.add_child(chip);
            return [minutes, chip];
        });
        column.add_child(chips);
        this.add_child(column);

        this.connect('destroy', () => this._stopTicking());
        this.update({});
    }

    get active() {
        return Boolean(this._state.active);
    }

    _isCurrent(minutes) {
        return this.active && Number(this._state.seconds ?? 0) === minutes * 60;
    }

    // Cliquer ailleurs que sur une puce bascule le mode.
    activate(_event) {
        this._toggle();
    }

    _toggle() {
        if (this._busy)
            return;
        this._run(() => this.active ? this._onStop() : this._onStart(-1));
    }

    async _run(callback) {
        this._busy = true;
        this.add_style_pseudo_class('insensitive');
        try {
            await callback();
        } finally {
            this._busy = false;
            this.remove_style_pseudo_class('insensitive');
            this.update(this._state);
        }
    }

    update(state) {
        this._state = state ?? {};
        const active = this.active;
        const until = Number(this._state.until ?? 0);

        if (active)
            this.add_style_class_name('saturn-awake-active');
        else
            this.remove_style_class_name('saturn-awake-active');

        this._headline.text = !active
            ? 'En veille normale'
            : until > 0
                ? `Jusqu'à ${GLib.DateTime.new_from_unix_local(Math.round(until)).format('%H:%M')}`
                : 'Jusqu\'à nouvel ordre';
        this._updateDetail();

        this._syncing = true;
        this._switch.state = active;
        this._syncing = false;
        for (const [minutes, chip] of this._chips) {
            if (this._isCurrent(minutes))
                chip.add_style_pseudo_class('checked');
            else
                chip.remove_style_pseudo_class('checked');
        }
        this.accessible_name = `Rester éveillé : ${this._headline.text}`;

        if (active && until > 0 && this._open)
            this._startTicking();
        else
            this._stopTicking();
    }

    _updateDetail() {
        const notice = this._state.notice;
        const until = Number(this._state.until ?? 0);
        if (notice) {
            this._detail.text = notice;
            this._detail.add_style_class_name('saturn-awake-notice');
            return;
        }
        this._detail.remove_style_class_name('saturn-awake-notice');
        if (!this.active) {
            this._detail.text = 'Choisissez une durée';
            return;
        }
        const left = until > 0
            ? `${formatRemaining(until - Date.now() / 1000)} RESTANT`
            : 'VEILLE BLOQUÉE';
        this._detail.text = this._state.display ? `${left}  ·  ÉCRAN ALLUMÉ` : left;
    }

    /** Le compte à rebours ne tourne que menu ouvert. */
    setOpen(open) {
        this._open = open;
        this.update(this._state);
    }

    _startTicking() {
        if (this._tickId)
            return;
        this._tickId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => {
            this._updateDetail();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _stopTicking() {
        if (this._tickId) {
            GLib.source_remove(this._tickId);
            this._tickId = 0;
        }
    }
});
