import GLib from 'gi://GLib';
import Shell from 'gi://Shell';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

export default class ZdorovoExtension extends Extension {
    enable() {
        this._dataDir = GLib.build_filenamev([GLib.get_user_data_dir(), 'zdorovo']);
        GLib.mkdir_with_parents(this._dataDir, 0o700);
        this._tracker = Shell.WindowTracker.get_default();
        this._shareHandles = new Set();
        this._remoteController = global.backend.get_remote_access_controller();
        this._remoteSignal = this._remoteController?.connect('new-handle', (_controller, handle) => {
            if (handle.isRecording)
                return;
            this._shareHandles.add(handle);
            handle.connect('stopped', () => this._shareHandles.delete(handle));
        }) ?? 0;
        this._tick();
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 1, () => this._tick());
    }

    disable() {
        if (this._timer) GLib.source_remove(this._timer);
        this._timer = null;
        if (this._remoteSignal && this._remoteController)
            this._remoteController.disconnect(this._remoteSignal);
        this._remoteSignal = 0;
        this._remoteController = null;
        this._shareHandles?.clear();
        this._shareHandles = null;
        this._tracker = null;
    }

    _path(name) {
        return GLib.build_filenamev([this._dataDir, name]);
    }

    _write(name, data) {
        try {
            GLib.file_set_contents(this._path(name), JSON.stringify(data));
        } catch (e) {
            console.error(`Здорово: cannot write ${name}: ${e}`);
        }
    }

    _tick() {
        const now = Date.now() / 1000;
        const win = global.display.focus_window;
        const app = win ? this._tracker.get_window_app(win) : null;
        const idle = global.backend.get_core_idle_monitor().get_idletime();
        this._write('activity.json', {
            timestamp: now,
            idle_ms: idle,
            app_id: app?.get_id() ?? win?.get_wm_class() ?? 'desktop',
            app_name: app?.get_name() ?? win?.get_wm_class() ?? 'Рабочий стол',
            wm_class: win?.get_wm_class() ?? '',
            fullscreen: win?.is_fullscreen() ?? false,
            screen_sharing: (this._shareHandles?.size ?? 0) > 0,
        });
        this._write('extension-heartbeat.json', {timestamp: now, version: 1});
        return GLib.SOURCE_CONTINUE;
    }
}
