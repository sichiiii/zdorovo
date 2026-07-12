#!/usr/bin/env python3
"""Small GTK 3 process that exposes Zdorovo in Ubuntu's AppIndicator area."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3, GLib, Gtk  # noqa: E402

APP_ID = "io.github.jabka.Zdorovo"
ICON_NAME = "io.github.jabka.Zdorovo-mint-v2"
OBJECT_PATH = "/io/github/jabka/Zdorovo"
ROOT = Path(__file__).resolve().parent
CONFIG_FILE = Path(os.environ.get("ZDOROVO_CONFIG_HOME", Path.home() / ".config" / "zdorovo")) / "config.json"


class ZdorovoIndicator:
    def __init__(self) -> None:
        icon_dir = Path.home() / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps"
        self.indicator = AyatanaAppIndicator3.Indicator.new(
            "zdorovo",
            ICON_NAME,
            AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_icon_theme_path(str(icon_dir))
        self.language = str(self._config().get("language", "en"))
        self.indicator.set_title("Zdorovo" if self.language == "en" else "Здорово")
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)

        self._syncing = False
        self._build_menu()
        self._sync_config()
        GLib.timeout_add_seconds(2, self._sync_config)

    def _label(self, english: str, russian: str) -> str:
        return english if self.language == "en" else russian

    def _build_menu(self) -> None:
        self.indicator.set_title(self._label("Zdorovo", "Здорово"))

        menu = Gtk.Menu()

        open_item = Gtk.MenuItem(label=self._label("Open Zdorovo", "Открыть Здорово"))
        open_item.connect("activate", lambda _item: self._open())
        menu.append(open_item)

        settings_item = Gtk.MenuItem(label=self._label("Settings", "Настройки"))
        settings_item.connect("activate", lambda _item: self._activate("show-page", "settings"))
        menu.append(settings_item)

        menu.append(Gtk.SeparatorMenuItem())
        self.pause_item = Gtk.CheckMenuItem(label=self._label("Pause reminders", "Приостановить напоминания"))
        self.pause_item.connect("toggled", self._pause_toggled)
        menu.append(self.pause_item)

        status_item = Gtk.MenuItem(
            label=self._label(
                "Screen time will continue to be counted", "Экранное время продолжает считаться"
            )
        )
        status_item.set_sensitive(False)
        menu.append(status_item)

        menu.append(Gtk.SeparatorMenuItem())
        quit_item = Gtk.MenuItem(label=self._label("Exit Zdorovo", "Выйти из Здорово"))
        quit_item.connect("activate", self._quit)
        menu.append(quit_item)

        menu.show_all()
        self.indicator.set_menu(menu)

    def _config(self) -> dict:
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _sync_config(self) -> bool:
        config = self._config()
        language = str(config.get("language", "en"))
        if language not in ("en", "ru"):
            language = "en"
        if language != self.language:
            self.language = language
            self._build_menu()
        paused = bool(config.get("manual_pause", False))
        if self.pause_item.get_active() != paused:
            self._syncing = True
            self.pause_item.set_active(paused)
            self._syncing = False
        self.indicator.set_attention_icon_full(
            ICON_NAME, self._label("Zdorovo — reminders paused", "Здорово — напоминания приостановлены")
        )
        self.indicator.set_status(
            AyatanaAppIndicator3.IndicatorStatus.ATTENTION
            if paused
            else AyatanaAppIndicator3.IndicatorStatus.ACTIVE
        )
        return GLib.SOURCE_CONTINUE

    def _pause_toggled(self, item: Gtk.CheckMenuItem) -> None:
        if not self._syncing:
            self._activate("set-manual-pause", item.get_active())

    def _open(self) -> None:
        subprocess.Popen(
            [str(ROOT / "launch.sh")],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def _quit(self, _item: Gtk.MenuItem) -> None:
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.PASSIVE)
        self._activate("quit", None)
        subprocess.run(
            ["systemctl", "--user", "stop", "zdorovo.service"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        Gtk.main_quit()

    def _activate(self, action: str, value: str | bool | None) -> None:
        parameters = (
            "[]"
            if value is None
            else (f"[<{'true' if value else 'false'}>]" if isinstance(value, bool) else f"[<'{value}'>]")
        )
        subprocess.run(
            [
                "gdbus",
                "call",
                "--session",
                "--dest",
                APP_ID,
                "--object-path",
                OBJECT_PATH,
                "--method",
                "org.gtk.Actions.Activate",
                action,
                parameters,
                "{}",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


if __name__ == "__main__":
    ZdorovoIndicator()
    Gtk.main()
