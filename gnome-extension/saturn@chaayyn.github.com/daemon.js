// Client D-Bus de saturnd, côté GNOME Shell.
//
// Aucune logique métier ici : on lit l'état des modules et on relaie les
// demandes de l'utilisateur au démon (org.saturn.Daemon1).

import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

export const BUS_NAME = 'org.saturn.Daemon';
export const OBJECT_PATH = '/org/saturn/Daemon';
export const INTERFACE = 'org.saturn.Daemon1';

const UI_BUS_NAME = 'org.saturn.Ui';
const UI_OBJECT_PATH = '/org/saturn/Ui';
const UI_INTERFACE = 'org.saturn.Ui1';

const CALL_TIMEOUT_MS = 10000;

/**
 * Appel D-Bus asynchrone sur le bus de session.
 *
 * @returns {Promise<any[]>} les arguments de retour, déjà convertis en JS
 */
export function callSession(name, path, iface, method, params = null, flags = Gio.DBusCallFlags.NO_AUTO_START) {
    return new Promise((resolve, reject) => {
        Gio.DBus.session.call(name, path, iface, method, params, null, flags,
            CALL_TIMEOUT_MS, null, (connection, result) => {
                try {
                    const reply = connection.call_finish(result);
                    resolve(reply ? reply.recursiveUnpack() : []);
                } catch (error) {
                    if (error instanceof GLib.Error)
                        Gio.DBusError.strip_remote_error(error);
                    reject(error);
                }
            });
    });
}

export class DaemonClient {
    /**
     * @param {object} handlers
     * @param {(available: boolean) => void} handlers.onAvailableChanged
     * @param {(id: string, module: object) => void} handlers.onModuleChanged
     */
    constructor({onAvailableChanged, onModuleChanged}) {
        this.available = false;
        this._onAvailableChanged = onAvailableChanged;
        this._onModuleChanged = onModuleChanged;

        this._watchId = Gio.bus_watch_name(Gio.BusType.SESSION, BUS_NAME,
            Gio.BusNameWatcherFlags.NONE,
            () => this._setAvailable(true),
            () => this._setAvailable(false));

        this._signalId = Gio.DBus.session.signal_subscribe(BUS_NAME, INTERFACE,
            'ModuleStateChanged', OBJECT_PATH, null, Gio.DBusSignalFlags.NONE,
            (_conn, _sender, _path, _iface, _signal, params) => {
                const [id, module] = params.recursiveUnpack();
                this._onModuleChanged?.(id, module);
            });
    }

    _setAvailable(available) {
        if (available === this.available)
            return;
        this.available = available;
        this._onAvailableChanged?.(available);
    }

    _call(method, params = null) {
        return callSession(BUS_NAME, OBJECT_PATH, INTERFACE, method, params);
    }

    async listModules() {
        const [modules] = await this._call('ListModules');
        return modules;
    }

    async getEnvironment() {
        const [environment] = await this._call('GetEnvironment');
        return environment;
    }

    async getVersion() {
        const [version] = await callSession(BUS_NAME, OBJECT_PATH,
            'org.freedesktop.DBus.Properties', 'Get',
            new GLib.Variant('(ss)', [INTERFACE, 'Version']));
        return version;
    }

    async setModuleEnabled(id, enabled) {
        const [module] = await this._call('SetModuleEnabled',
            new GLib.Variant('(sb)', [id, enabled]));
        return module;
    }

    /** Le démon peut-il être lancé par activation D-Bus (fichier .service installé) ? */
    async isActivatable() {
        const [names] = await callSession('org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'ListActivatableNames');
        return names.includes(BUS_NAME);
    }

    /** Démarre saturnd : activation D-Bus si possible, sinon l'exécutable installé. */
    async start() {
        if (await this.isActivatable()) {
            await callSession('org.freedesktop.DBus', '/org/freedesktop/DBus',
                'org.freedesktop.DBus', 'StartServiceByName',
                new GLib.Variant('(su)', [BUS_NAME, 0]));
            return;
        }
        spawn(['saturnd']);
    }

    destroy() {
        if (this._watchId) {
            Gio.bus_unwatch_name(this._watchId);
            this._watchId = 0;
        }
        if (this._signalId) {
            Gio.DBus.session.signal_unsubscribe(this._signalId);
            this._signalId = 0;
        }
        this._onAvailableChanged = null;
        this._onModuleChanged = null;
    }
}

/**
 * Demande quelque chose à l'interface Qt. Si elle ne tourne pas, D-Bus la lance
 * (activation installée par scripts/install.sh) ; à défaut, on lance `saturn`.
 */
async function callUi(method, params, fallbackArgv) {
    try {
        await callSession(UI_BUS_NAME, UI_OBJECT_PATH, UI_INTERFACE, method, params,
            Gio.DBusCallFlags.NONE);
    } catch {
        spawn(fallbackArgv);
    }
}

/** Ouvre la fenêtre de réglages (sur un module précis si `moduleId` est donné). */
export function openSettings(moduleId = '') {
    return callUi('OpenSettings', new GLib.Variant('(s)', [moduleId]),
        moduleId ? ['saturn', '--settings', moduleId] : ['saturn', '--settings']);
}

/** Ouvre la fenêtre d'historique du presse-papiers. */
export function openClipboard() {
    return callUi('OpenClipboard', null, ['saturn', '--clipboard']);
}

/** Ouvre le bloc-notes. */
export function openScratchpad() {
    return callUi('OpenScratchpad', null, ['saturn', '--scratchpad']);
}

/** Cherche un exécutable dans le PATH, puis dans ~/.local/bin (installé par scripts/install.sh). */
export function findProgram(name) {
    const inPath = GLib.find_program_in_path(name);
    if (inPath)
        return inPath;
    const local = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', name]);
    return GLib.file_test(local, GLib.FileTest.IS_EXECUTABLE) ? local : null;
}

export function spawn(argv) {
    const program = findProgram(argv[0]);
    if (!program)
        throw new Error(`${argv[0]} introuvable : lancez scripts/install.sh`);
    Gio.Subprocess.new([program, ...argv.slice(1)], Gio.SubprocessFlags.NONE);
}
