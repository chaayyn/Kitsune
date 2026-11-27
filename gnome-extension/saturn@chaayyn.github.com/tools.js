// Outils rapides du menu : deux tuiles (Pipette, Nettoyage) et le nuancier
// des dernières couleurs prélevées. Rien n'est calculé ici : les tuiles
// déclenchent les actions de saturnd.

import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import Pango from 'gi://Pango';
import St from 'gi://St';

import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';

/** Nombre de pastilles affichées dans le menu. */
const SWATCHES = 8;

function text(value, styleClass) {
    const label = new St.Label({text: value, style_class: styleClass, x_align: Clutter.ActorAlign.START});
    label.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
    return label;
}

/** Pastille ronde de la couleur donnée, en icône (pour l'OSD de GNOME). */
export function swatchIcon(hex) {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">
        <circle cx="48" cy="48" r="40" fill="${hex}" stroke="rgba(255,255,255,0.35)" stroke-width="2"/></svg>`;
    return new Gio.BytesIcon({bytes: new GLib.Bytes(new TextEncoder().encode(svg))});
}

function tile(eyebrow, title, onClicked) {
    const box = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL, x_expand: true});
    const top = new St.BoxLayout({x_expand: true});
    top.add_child(text(eyebrow, 'saturn-tile-eyebrow'));
    top.add_child(new St.Widget({x_expand: true}));
    const accent = new St.Widget({style_class: 'saturn-tile-dot', y_align: Clutter.ActorAlign.CENTER});
    top.add_child(accent);
    box.add_child(top);
    box.add_child(text(title, 'saturn-tile-title'));
    const hint = text('', 'saturn-tile-hint');
    box.add_child(hint);
    const button = new St.Button({
        child: box,
        style_class: 'saturn-tile',
        x_expand: true,
        can_focus: true,
        accessible_name: title,
    });
    button.connect('clicked', onClicked);
    button.hint = hint;
    button.dot = accent;
    return button;
}

export const ToolsItem = GObject.registerClass(
class ToolsItem extends PopupMenu.PopupBaseMenuItem {
    /**
     * @param {object} handlers
     * @param {() => void} handlers.onPick
     * @param {() => void} handlers.onClean
     * @param {(hex: string) => void} handlers.onCopy
     */
    _init({onPick, onClean, onCopy}) {
        super._init({style_class: 'saturn-tools', reactive: false, can_focus: false});
        this._onCopy = onCopy;

        const column = new St.BoxLayout({orientation: Clutter.Orientation.VERTICAL, x_expand: true});
        const tiles = new St.BoxLayout({x_expand: true, style_class: 'saturn-tiles'});
        this._pick = tile('PIPETTE', 'Prélever', onPick);
        this._pick.hint.text = 'SUPER+MAJ+C';
        this._clean = tile('NETTOYAGE', 'Voile noir', onClean);
        this._clean.dot.visible = false;  // seule la pipette montre une pastille (dernière couleur)
        tiles.add_child(this._pick);
        tiles.add_child(this._clean);
        column.add_child(tiles);

        this._swatches = new St.BoxLayout({x_expand: true, style_class: 'saturn-swatches'});
        column.add_child(this._swatches);
        this.add_child(column);
        this.setColors([]);
    }

    setAvailable(picker, cleaning) {
        this._pick.visible = picker;
        this._clean.visible = cleaning;
        this._swatches.visible = picker && this._swatches.get_n_children() > 0;
        this.visible = picker || cleaning;
    }

    setCleaningHint(hint) {
        this._clean.hint.text = hint;
    }

    /** @param {{hex: string}[]} colors du plus récent au plus ancien */
    setColors(colors) {
        this._swatches.destroy_all_children();
        for (const {hex} of colors.slice(0, SWATCHES)) {
            const swatch = new St.Button({
                style_class: 'saturn-swatch',
                style: `background-color: ${hex};`,
                can_focus: true,
                accessible_name: `Copier ${hex}`,
                y_align: Clutter.ActorAlign.CENTER,
            });
            swatch.connect('clicked', () => this._onCopy(hex));
            this._swatches.add_child(swatch);
        }
        this._swatches.add_child(new St.Widget({x_expand: true}));
        const last = colors[0]?.hex;
        this._pick.dot.style = last ? `background-color: ${last};` : '';
        this._swatches.visible = this._pick.visible && colors.length > 0;
    }
});
