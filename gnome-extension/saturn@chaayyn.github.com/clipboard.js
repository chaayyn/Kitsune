// Pont presse-papiers pour GNOME Wayland.
//
// Sous GNOME, seul le Shell peut lire le presse-papiers d'une autre appli.
// Quand le module « clipboard » de saturnd tourne, l'extension lui pousse
// chaque copie (action « push ») et applique les écritures qu'il demande
// (évènement « write » : recopie depuis l'historique, lien nettoyé, vidage).

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import St from 'gi://St';

import {BUS_NAME, INTERFACE, OBJECT_PATH, callSession} from './daemon.js';

const MODULE_ID = 'clipboard';
const URI_LIST = 'text/uri-list';
const IMAGE_MIMES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif', 'image/bmp'];
const TEXT_MIMES = ['text/plain;charset=utf-8', 'UTF8_STRING', 'text/plain', 'STRING', 'TEXT'];
const MAX_IMAGE_BYTES = 25 * 1024 * 1024;

const decoder = new TextDecoder();
const encoder = new TextEncoder();

function getContent(clipboard, mime) {
    return new Promise(resolve =>
        clipboard.get_content(St.ClipboardType.CLIPBOARD, mime, (_c, bytes) => resolve(bytes)));
}

function getText(clipboard) {
    return new Promise(resolve =>
        clipboard.get_text(St.ClipboardType.CLIPBOARD, (_c, text) => resolve(text)));
}

export class ClipboardBridge {
    constructor() {
        this._active = false;
        this._ownerChangedId = 0;
        this._storeImages = true;
        this._storeFiles = true;

        const bus = Gio.DBus.session;
        this._eventId = bus.signal_subscribe(BUS_NAME, INTERFACE, 'ModuleEvent', OBJECT_PATH,
            null, Gio.DBusSignalFlags.NONE, (...args) => {
                const [id, event, data] = args[5].recursiveUnpack();
                // Les autres modules (pipette…) écrivent aussi par ici, même sans historique.
                if (event === 'write' && (id !== MODULE_ID || this._active))
                    this._write(data);
            });
        this._settingId = bus.signal_subscribe(BUS_NAME, INTERFACE, 'SettingChanged', OBJECT_PATH,
            null, Gio.DBusSignalFlags.NONE, (...args) => {
                const [id, key, value] = args[5].recursiveUnpack();
                if (id === MODULE_ID)
                    this._applySetting(key, value);
            });
    }

    /** Suit le presse-papiers seulement si le module tourne et que la session est Wayland. */
    setActive(active) {
        if (active === this._active)
            return;
        this._active = active;
        const selection = global.display.get_selection();
        if (active) {
            this._ownerChangedId = selection.connect('owner-changed', (_sel, type, source) => {
                if (type === Meta.SelectionType.SELECTION_CLIPBOARD && source)
                    this._capture().catch(error => logError(error, 'Saturn : copie non relayée'));
            });
            this._loadSettings().catch(logError);
        } else if (this._ownerChangedId) {
            selection.disconnect(this._ownerChangedId);
            this._ownerChangedId = 0;
        }
    }

    async _loadSettings() {
        const [settings] = await callSession(BUS_NAME, OBJECT_PATH, INTERFACE, 'GetSettings',
            new GLib.Variant('(s)', [MODULE_ID]));
        for (const [key, value] of Object.entries(settings))
            this._applySetting(key, value);
    }

    _applySetting(key, value) {
        if (key === 'store_images')
            this._storeImages = value;
        else if (key === 'store_files')
            this._storeFiles = value;
    }

    async _capture() {
        const clipboard = St.Clipboard.get_default();
        const mimes = clipboard.get_mimetypes(St.ClipboardType.CLIPBOARD);
        const params = {mimes: new GLib.Variant('as', mimes)};

        const image = IMAGE_MIMES.find(mime => mimes.includes(mime));
        if (this._storeFiles && mimes.includes(URI_LIST)) {
            const bytes = await getContent(clipboard, URI_LIST);
            if (!bytes)
                return;
            params.uris = new GLib.Variant('s', decoder.decode(bytes.toArray()));
        } else if (this._storeImages && image) {
            const bytes = await getContent(clipboard, image);
            if (!bytes || bytes.get_size() === 0 || bytes.get_size() > MAX_IMAGE_BYTES)
                return;
            params.image = GLib.Variant.new_from_bytes(new GLib.VariantType('ay'), bytes, true);
            params.mime = new GLib.Variant('s', image);
        } else if (TEXT_MIMES.some(mime => mimes.includes(mime))) {
            const text = await getText(clipboard);
            if (!text)
                return;
            params.text = new GLib.Variant('s', text);
        } else {
            return;
        }

        await callSession(BUS_NAME, OBJECT_PATH, INTERFACE, 'CallAction',
            new GLib.Variant('(ssa{sv})', [MODULE_ID, 'push', params]));
    }

    _write(data) {
        const clipboard = St.Clipboard.get_default();
        const type = St.ClipboardType.CLIPBOARD;
        if (data.clear)
            clipboard.set_text(type, '');
        else if (data.text !== undefined)
            clipboard.set_text(type, data.text);
        else if (data.image !== undefined)
            clipboard.set_content(type, data.mime ?? 'image/png', new GLib.Bytes(data.image));
        else if (data.uris !== undefined)
            clipboard.set_content(type, URI_LIST, new GLib.Bytes(encoder.encode(data.uris)));
    }

    destroy() {
        this.setActive(false);
        for (const id of [this._eventId, this._settingId])
            Gio.DBus.session.signal_unsubscribe(id);
        this._eventId = this._settingId = 0;
    }
}
