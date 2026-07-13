#!/usr/bin/env python3
"""Build a small demo profile and capture the main Zdorovo pages."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "screenshots"
PROFILE = Path(tempfile.mkdtemp(prefix="zdorovo-screenshots-"))
os.environ["ZDOROVO_CONFIG_HOME"] = str(PROFILE / "config")
os.environ["ZDOROVO_DATA_HOME"] = str(PROFILE / "data")
sys.path.insert(0, str(ROOT))

import gi  # noqa: E402

gi.require_version("Gsk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, Graphene, Gsk, Gtk  # noqa: E402

import healthbreak  # noqa: E402

CAPTURES = (
    ("overview", "today", False),
    ("achievements", "achievements", True),
    ("breathing", "breathing", False),
    ("analytics", "analytics", True),
    ("habits", "habits", False),
    ("settings", "settings", True),
)


def seed_demo(app: healthbreak.ZdorovoApplication, language: str = "en") -> None:
    app.config.data.update(
        {
            "language": language,
            "language_selected": True,
            "dark_mode": False,
            "theme_mode": "light",
            "notification_center_initialized": True,
            "wellness_reminders_enabled": True,
        }
    )
    app.config.save()
    db = app.db
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    apps = (
        ("google-chrome.desktop", "Google Chrome", 0.34),
        ("code_code.desktop", "Visual Studio Code", 0.27),
        ("org.gnome.Ptyxis.desktop", "Terminal", 0.16),
        ("org.telegram.desktop", "Telegram", 0.11),
        ("org.gnome.Nautilus.desktop", "Files", 0.07),
        ("io.github.jabka.Zdorovo.desktop", "Zdorovo", 0.05),
    )
    with db.conn:
        for day_offset in range(7):
            day = (now.date() - timedelta(days=6 - day_offset)).isoformat()
            total = (2.4 + day_offset * 0.28) * 3600
            for app_id, app_name, share in apps:
                db.conn.execute(
                    "INSERT INTO daily_app(day, app_id, app_name, seconds) VALUES(?,?,?,?)",
                    (day, app_id, app_name, total * share),
                )
        today_start = datetime.combine(now.date(), datetime.min.time())
        for hour in range(8, 18):
            cursor = today_start + timedelta(hours=hour)
            for index, (app_id, app_name, share) in enumerate(apps[:4]):
                duration = 2700 * share
                started = cursor + timedelta(seconds=index * 540)
                db.conn.execute(
                    """INSERT INTO usage_segments(started_at, ended_at, app_id, app_name)
                       VALUES(?,?,?,?)""",
                    (
                        started.timestamp(),
                        (started + timedelta(seconds=duration)).timestamp(),
                        app_id,
                        app_name,
                    ),
                )
        kinds = ("eyes", "general", "neck", "eyes", "breathing", "general", "wrists")
        for day_offset in range(7):
            stamp = now - timedelta(days=6 - day_offset, hours=2)
            for index, kind in enumerate(kinds[: 3 + day_offset % 5]):
                db.conn.execute(
                    """INSERT INTO reminder_events(created_at, kind, action, duration_seconds)
                       VALUES(?,?,?,?)""",
                    (stamp.timestamp() + index * 90, kind, "done", 60 + index * 20),
                )
        for day_offset, values in enumerate(((4, 3, 4, 2), (3, 2, 3, 2), (2, 2, 2, 1), (2, 1, 2, 1))):
            stamp = now - timedelta(days=3 - day_offset, hours=1)
            db.conn.execute(
                """INSERT INTO wellness_checkins(created_at, headache, eyes, neck, back)
                   VALUES(?,?,?,?,?)""",
                (stamp.timestamp(), *values),
            )
        habits = ("daily-movement", "breathing-pause")
        for day_offset in range(6):
            for habit_id in habits:
                db.conn.execute(
                    "INSERT INTO habit_events(created_at, habit_id, amount) VALUES(?,?,1)",
                    ((now - timedelta(days=day_offset)).timestamp(), habit_id),
                )
    db.evaluate_achievements(now=time.time())
    db.add_notification(
        "achievement",
        "New achievement",
        "Work rhythm · Level II is now unlocked.",
        "achievements",
        notification_id="demo-achievement",
    )
    db.add_notification(
        "habit",
        "Walk or move",
        "Your daily movement goal is ready when you are.",
        "habits",
        notification_id="demo-habit",
    )


def save_window(window: Gtk.Window, path: Path) -> None:
    target = window.get_child() or window
    width, height = target.get_width(), target.get_height()
    paintable = Gtk.WidgetPaintable.new(target)
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, float(width), float(height))
    node = snapshot.to_node()
    if node is None:
        raise RuntimeError(f"could not snapshot {path.name}")
    surface = window.get_surface()
    if surface is None:
        raise RuntimeError("window has no surface")
    renderer = Gsk.Renderer.new_for_surface(surface)
    bounds = Graphene.Rect()
    bounds.init(0, 0, width, height)
    try:
        texture = renderer.render_texture(node, bounds)
        if not texture.save_to_png(str(path)):
            raise RuntimeError(f"could not save {path}")
    finally:
        renderer.unrealize()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", choices=[name for name, _page, _dark in CAPTURES])
    parser.add_argument("--language", choices=("en", "ru"), default="en")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    args = parser.parse_args()
    if not args.page:
        try:
            for name, _page, _dark in CAPTURES:
                subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--page",
                        name,
                        "--language",
                        args.language,
                        "--width",
                        str(args.width),
                        "--height",
                        str(args.height),
                    ],
                    check=True,
                )
            return 0
        finally:
            shutil.rmtree(PROFILE, ignore_errors=True)

    captures = tuple(capture for capture in CAPTURES if capture[0] == args.page)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    app = healthbreak.ZdorovoApplication()
    seed_demo(app, args.language)
    state = {"index": 0}

    def capture_current() -> bool:
        window = app.window
        if window is None:
            return GLib.SOURCE_REMOVE
        name, _page, _dark = captures[state["index"]]
        suffix = "" if args.language == "en" else f"-{args.language}"
        save_window(window, OUTPUT / f"{name}{suffix}.png")
        state["index"] += 1
        if state["index"] >= len(captures):
            app.quit()
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(80, show_next)
        return GLib.SOURCE_REMOVE

    def show_next() -> bool:
        window = app.window
        if window is None:
            return GLib.SOURCE_REMOVE
        _name, page, dark = captures[state["index"]]
        window.set_visible(False)
        app.config.data["dark_mode"] = dark
        app.config.data["theme_mode"] = "dark" if dark else "light"
        app.apply_color_scheme()
        window.add_css_class("dark-mode") if dark else window.remove_css_class("dark-mode")
        window.backdrop.set_dark(dark)
        window.stack.set_visible_child_name(page)
        window.refresh(rebuild_lists=True)
        window.present()
        window.queue_draw()
        GLib.timeout_add(650, capture_current)
        return GLib.SOURCE_REMOVE

    def wait_for_window() -> bool:
        if app.window is None:
            return GLib.SOURCE_CONTINUE
        app.window.set_default_size(args.width, args.height)
        app.window.present()
        GLib.timeout_add(700, show_next)
        return GLib.SOURCE_REMOVE

    GLib.timeout_add(200, wait_for_window)
    try:
        return app.run([])
    finally:
        shutil.rmtree(PROFILE, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
