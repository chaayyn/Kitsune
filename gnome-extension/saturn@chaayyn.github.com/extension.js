// Extension GNOME Shell de Saturn.
//
// Remplace l'icône de la zone de notification (qui exige l'extension
// AppIndicator) par un vrai bouton de la barre du haut, avec un menu ancré.
// Le nom org.saturn.Shell signale sa présence à l'interface Qt, qui masque
// alors sa propre icône.

import Gio from 'gi://Gio';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

import {SaturnIndicator} from './indicator.js';

const SHELL_BUS_NAME = 'org.saturn.Shell';

export default class SaturnExtension extends Extension {
    enable() {
        this._indicator = new SaturnIndicator(this);
        Main.panel.addToStatusArea(this.uuid, this._indicator);
        this._nameId = Gio.bus_own_name(Gio.BusType.SESSION, SHELL_BUS_NAME,
            Gio.BusNameOwnerFlags.NONE, null, null, null);
    }

    disable() {
        if (this._nameId) {
            Gio.bus_unown_name(this._nameId);
            this._nameId = 0;
        }
        this._indicator?.destroy();
        this._indicator = null;
    }
}
