import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import training as TRAINING

TMP = tempfile.TemporaryDirectory()
os.environ["ZDOROVO_CONFIG_HOME"] = str(Path(TMP.name) / "config")
os.environ["ZDOROVO_DATA_HOME"] = str(Path(TMP.name) / "data")
SPEC = importlib.util.spec_from_file_location("healthbreak", Path(__file__).parents[1] / "healthbreak.py")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules["healthbreak"] = MODULE
SPEC.loader.exec_module(MODULE)


class CoreTests(unittest.TestCase):
    def setUp(self):
        for path in (
            MODULE.STATE_FILE,
            MODULE.REMINDER_FILE,
            MODULE.RESPONSE_FILE,
            MODULE.ACTIVITY_FILE,
        ):
            path.unlink(missing_ok=True)

    def test_deep_merge_preserves_defaults(self):
        value = MODULE.deep_merge(
            MODULE.DEFAULT_CONFIG, {"dark_mode": True, "reminders": {"eyes": {"interval_minutes": 25}}}
        )
        self.assertTrue(value["dark_mode"])
        self.assertEqual(value["reminders"]["eyes"]["interval_minutes"], 25)
        self.assertIn("general", value["reminders"])
        self.assertTrue(value["wellness_checkin_enabled"])
        self.assertEqual(value["color_theme"], "teal")
        self.assertFalse(value["sidebar_collapsed"])

    def test_accent_palettes_render_and_validate(self):
        css = "@define-color accent #327F79; border: rgba(50,127,121,0.26);"
        burgundy = MODULE.render_palette_css(css, "burgundy")
        gray = MODULE.render_palette_css(css, "gray")
        self.assertIn("#8B3A4A", burgundy)
        self.assertIn("rgba(139,58,74,0.26)", burgundy)
        self.assertIn("#646E78", gray)
        self.assertNotEqual(burgundy, gray)
        self.assertEqual(MODULE.normalize_color_theme("unknown"), "teal")

        full_css = (Path(__file__).parents[1] / "assets" / "style.css").read_text()
        for palette in ("burgundy", "gray"):
            rendered = MODULE.render_palette_css(full_css, palette)
            for teal_token in (
                "#327F79",
                "#246B66",
                "#2B756F",
                "#4B9B94",
                "#9ED8D2",
                "#294D4A",
                "#203A38",
                "rgba(43, 117, 111,",
            ):
                self.assertNotIn(teal_token.lower(), rendered.lower(), (palette, teal_token))

        svg = '<path stroke="#327F79"/>'
        self.assertIn("#8B3A4A", MODULE.render_palette_svg(svg, "burgundy"))
        self.assertIn("#646E78", MODULE.render_palette_svg(svg, "gray"))

    def test_fullscreen_viewing_counts_past_idle_threshold(self):
        self.assertTrue(MODULE.screen_is_being_used(3600, 60, True))
        self.assertFalse(MODULE.screen_is_being_used(61, 60, False))
        config = MODULE.Config()
        MODULE.atomic_json(
            MODULE.ACTIVITY_FILE,
            {
                "timestamp": MODULE.time.time(),
                "idle_ms": 3_600_000,
                "app_id": "browser.desktop",
                "app_name": "Browser",
                "fullscreen": True,
                "screen_sharing": False,
            },
        )
        db = MODULE.UsageDatabase(Path(TMP.name) / "fullscreen.sqlite3")
        activity = MODULE.Scheduler(config, db, lambda _payload: None).read_activity()
        self.assertTrue(activity.active)
        self.assertTrue(activity.fullscreen)
        self.assertEqual(activity.app_id, "browser.desktop")

    def test_hidden_status_banners_do_not_reserve_space(self):
        calls = []
        revealer = SimpleNamespace(
            set_reveal_child=lambda value: calls.append(("reveal", value)),
            set_visible=lambda value: calls.append(("visible", value)),
        )
        MODULE.set_status_banner_state(revealer, False)
        self.assertEqual(calls, [("reveal", False), ("visible", False)])

    def test_database_aggregates_per_app(self):
        db = MODULE.UsageDatabase(Path(TMP.name) / "test.sqlite3")
        now = 1_800_000_000.0
        db.record_tick(now, "firefox.desktop", "Firefox", 5)
        db.record_tick(now + 5, "firefox.desktop", "Firefox", 5)
        day = MODULE.datetime.fromtimestamp(now).date().isoformat()
        self.assertEqual(db.total_for_day(day), 10)
        self.assertEqual(db.top_apps(days=9999)[0]["app_name"], "Firefox")

    def test_database_exposes_daily_app_segments(self):
        db = MODULE.UsageDatabase(Path(TMP.name) / "segments.sqlite3")
        now = MODULE.time.time()
        db.record_tick(now, "browser.desktop", "Browser", 7)
        db.record_tick(now, "editor.desktop", "Editor", 3)
        rows = db.daily_app_totals(7)
        totals = {row["app_id"]: row["seconds"] for row in rows}
        self.assertEqual(totals["browser.desktop"], 7)
        self.assertEqual(totals["editor.desktop"], 3)

    def test_hourly_activity_splits_segments_at_hour_boundary(self):
        db = MODULE.UsageDatabase(Path(TMP.name) / "hourly.sqlite3")
        day = MODULE.datetime.now().date()
        boundary = MODULE.datetime.combine(day, MODULE.datetime.min.time()).timestamp() + 11 * 3600
        db.conn.execute(
            "INSERT INTO usage_segments(started_at, ended_at, app_id, app_name) VALUES(?,?,?,?)",
            (boundary - 10, boundary + 15, "browser.desktop", "Browser"),
        )
        db.conn.commit()
        rows = db.hourly_app_totals(day.isoformat())
        totals = {row["hour"]: row["seconds"] for row in rows}
        self.assertEqual(totals[10], 10)
        self.assertEqual(totals[11], 15)

    def test_duration_format(self):
        self.assertEqual(MODULE.format_duration(20), "20 сек")
        self.assertEqual(MODULE.format_duration(3661), "1 ч 01 мин")
        self.assertEqual(MODULE.format_precise_duration(90), "1 мин 30 сек")
        self.assertEqual(MODULE.notification_badge_text(1), "1")
        self.assertEqual(MODULE.notification_badge_text(9), "9")
        self.assertEqual(MODULE.notification_badge_text(10), "9+")
        preset = {"inhale": 4, "exhale": 6}
        self.assertEqual(MODULE.breathing_phase(preset, 0)[0], "ready")
        self.assertEqual(MODULE.breathing_phase(preset, 2), ("inhale", 0.5))
        self.assertEqual(MODULE.breathing_phase(preset, 7), ("exhale", 0.5))

    def test_achievement_series_fill_the_grid_with_reachable_targets(self):
        grouped = {}
        for achievement in MODULE.ACHIEVEMENTS:
            grouped.setdefault(achievement["series"], []).append(achievement)
        self.assertTrue(all(len(series) == 8 for series in grouped.values()))
        upper_bounds = {
            "rhythm": 1000,
            "eyes": 500,
            "movement": 500,
            "breathing": 300,
            "habits": 1000,
            "variety": len(MODULE.REMINDER_META),
            "streak": 365,
        }
        for name, series in grouped.items():
            targets = [int(item["target"]) for item in series]
            self.assertEqual(targets, sorted(set(targets)), name)
            self.assertLessEqual(targets[-1], upper_bounds[name], name)

    def test_automatic_theme_schedule_crosses_midnight(self):
        def moment(hour, minute=0):
            return MODULE.datetime(2026, 7, 13, hour, minute)

        self.assertTrue(MODULE.automatic_theme_is_dark(moment(6, 59), "07:00", "21:00"))
        self.assertFalse(MODULE.automatic_theme_is_dark(moment(7), "07:00", "21:00"))
        self.assertFalse(MODULE.automatic_theme_is_dark(moment(20, 59), "07:00", "21:00"))
        self.assertTrue(MODULE.automatic_theme_is_dark(moment(21), "07:00", "21:00"))
        self.assertFalse(MODULE.automatic_theme_is_dark(moment(23), "20:00", "06:00"))
        self.assertTrue(MODULE.automatic_theme_is_dark(moment(12), "20:00", "06:00"))
        self.assertEqual(MODULE.normalize_clock("7:5", "00:00"), "07:05")
        self.assertEqual(MODULE.normalize_clock("25:00", "07:00"), "07:00")

    def test_application_accent_is_compatible_with_gtk_414(self):
        css = (Path(__file__).parents[1] / "assets" / "style.css").read_text()
        self.assertIn("@define-color accent #327F79", css)
        self.assertIn("switch:checked", css)
        self.assertNotIn(":root", css)
        self.assertNotIn("--accent", css)
        self.assertNotIn("#E95420", css)
        source = (Path(__file__).parents[1] / "healthbreak.py").read_text()
        self.assertIn("Gtk.STYLE_PROVIDER_PRIORITY_USER + 1", source)

    def test_calendar_range_and_narrow_pages_remain_visible(self):
        css = (Path(__file__).parents[1] / "assets" / "style.css").read_text()
        source = (Path(__file__).parents[1] / "healthbreak.py").read_text()
        self.assertIn("if range_start <= target <= range_end:", source)
        self.assertIn(".range-day.range-inside { color: white; background: #327F79; }", css)
        self.assertIn(".range-day.range-start.range-end { border-radius: 8px; }", css)
        self.assertIn("responsive_page = Adw.BreakpointBin()", source)
        self.assertIn("hscrollbar_policy=Gtk.PolicyType.NEVER", source)
        self.assertIn("label=note, xalign=0, wrap=True", source)
        self.assertIn("scrollbar.vertical {\n  min-width: 3px;", css)
        self.assertIn("border: 1px solid rgba(50,127,121,0.26);", css)
        self.assertIn(".palette-picker button", css)
        self.assertIn("class PaletteEmblem", source)
        self.assertIn("behavior_grid.set_homogeneous(False)", source)
        self.assertIn('parse("max-width: 850sp")', source)
        self.assertIn("levels.set_min_children_per_line(4)", source)
        self.assertIn('levels, "min-children-per-line", 2', source)
        self.assertIn('levels_frame, "height-request", 938', source)

    def test_system_notifications_include_visible_details(self):
        source = (Path(__file__).parents[1] / "healthbreak.py").read_text()
        self.assertIn('settings.set_boolean("force-expanded", True)', source)
        self.assertIn("notification.set_body", source)
        self.assertIn("Gio.NotificationPriority.HIGH", source)
        self.assertIn("notification.set_icon", source)

    def test_guided_steps_cover_the_whole_timer(self):
        self.assertEqual(MODULE.guided_step_seconds(45, 5, [10, 5, 10, 5, 15]), [10, 5, 10, 5, 15])
        self.assertEqual(sum(MODULE.guided_step_seconds(181, 4)), 181)

    def test_exercise_analytics_records_real_guided_time(self):
        db = MODULE.UsageDatabase(Path(TMP.name) / "exercise_analytics.sqlite3")
        db.log_reminder("eyes", "done", duration_seconds=42)
        db.log_reminder("eyes", "snooze")
        overview = db.exercise_overview(7)
        self.assertEqual(overview["done"], 1)
        self.assertEqual(overview["snoozed"], 1)
        self.assertEqual(overview["seconds"], 42)
        self.assertEqual(db.exercise_by_kind(7)[0]["kind"], "eyes")

    def test_drops_are_distributed_across_active_day(self):
        config = MODULE.Config()
        config.data["reminders"]["drops"]["times_per_day"] = 4
        db = MODULE.UsageDatabase(Path(TMP.name) / "drops.sqlite3")
        scheduler = MODULE.Scheduler(config, db, lambda _payload: None)
        self.assertEqual(scheduler._target_seconds("drops"), 7200)

    def test_every_activity_has_config_and_instructions(self):
        self.assertEqual(set(MODULE.DEFAULT_CONFIG["reminders"]), set(MODULE.REMINDER_META))
        for kind, meta in MODULE.REMINDER_META.items():
            self.assertTrue(meta["title"], kind)
            self.assertTrue(meta["steps"], kind)
            self.assertTrue((MODULE.ROOT / "assets" / meta["image"]).is_file(), kind)

    def test_reminder_done_resets_accrued_time(self):
        config = MODULE.Config()
        db = MODULE.UsageDatabase(Path(TMP.name) / "reminder.sqlite3")
        shown = []
        scheduler = MODULE.Scheduler(config, db, shown.append)
        original_pause = MODULE.pause_media_players
        MODULE.pause_media_players = lambda: 0
        try:
            scheduler.trigger("eyes")
            self.assertEqual(shown[0]["kind"], "eyes")
            MODULE.atomic_json(MODULE.RESPONSE_FILE, {"id": shown[0]["id"], "action": "done"})
            scheduler._consume_response()
            self.assertEqual(scheduler.state["accrued"]["eyes"], 0)
            self.assertIsNone(scheduler.state["active_id"])
            self.assertEqual(scheduler.state["rotation"]["eyes"], 1)
            self.assertEqual(scheduler.next_title("eyes"), "Gentle focus change")
        finally:
            MODULE.pause_media_players = original_pause

    def test_process_start_never_shows_a_persisted_due_reminder(self):
        config = MODULE.Config()
        persisted = {
            "accrued": {kind: 999999.0 for kind in MODULE.REMINDER_META},
            "active_id": "stale-reminder",
        }
        MODULE.atomic_json(MODULE.STATE_FILE, persisted)
        db = MODULE.UsageDatabase(Path(TMP.name) / "startup_schedule.sqlite3")
        shown = []
        scheduler = MODULE.Scheduler(config, db, shown.append)
        self.assertIsNone(scheduler.state["active_id"])
        self.assertTrue(all(value == 0 for value in scheduler.state["accrued"].values()))
        scheduler._maybe_show(MODULE.time.time())
        self.assertEqual(shown, [])
        self.assertEqual(scheduler.next_due("eyes"), scheduler._target_seconds("eyes"))

    def test_snooze_uses_configured_global_quiet_time(self):
        config = MODULE.Config()
        config.data["snooze_minutes"] = 2
        db = MODULE.UsageDatabase(Path(TMP.name) / "global_snooze.sqlite3")
        shown = []
        scheduler = MODULE.Scheduler(config, db, shown.append)
        original_pause = MODULE.pause_media_players
        MODULE.pause_media_players = lambda: 0
        try:
            scheduler.state["accrued"]["general"] = scheduler._target_seconds("general")
            scheduler.state["accrued"]["neck"] = scheduler._target_seconds("neck")
            scheduler._maybe_show(MODULE.time.time())
            first = shown[-1]
            MODULE.atomic_json(MODULE.RESPONSE_FILE, {"id": first["id"], "action": "snooze"})
            scheduler._consume_response()
            scheduler._maybe_show(MODULE.time.time() + 2)
            self.assertEqual(len(shown), 1)
            self.assertGreaterEqual(scheduler.state["quiet_until"] - MODULE.time.time(), 119)
            self.assertGreaterEqual(scheduler.next_due("neck"), 119)
        finally:
            MODULE.pause_media_players = original_pause

    def test_repeated_activity_waits_for_a_different_one_nearby(self):
        config = MODULE.Config()
        for kind in config.data["reminders"]:
            config.data["reminders"][kind]["enabled"] = kind in ("eyes", "general")
        db = MODULE.UsageDatabase(Path(TMP.name) / "fair_reminder_order.sqlite3")
        shown = []
        scheduler = MODULE.Scheduler(config, db, shown.append)
        original_pause = MODULE.pause_media_players
        MODULE.pause_media_players = lambda: []
        try:
            now = MODULE.time.time()
            scheduler.state["last_completed_kind"] = "eyes"
            scheduler.state["accrued"]["eyes"] = scheduler._target_seconds("eyes")
            scheduler.state["accrued"]["general"] = scheduler._target_seconds("general") - 10 * 60
            scheduler._maybe_show(now)
            self.assertEqual(shown, [])
            self.assertEqual(scheduler.next_due("eyes"), 10 * 60)

            scheduler.state["accrued"]["general"] = scheduler._target_seconds("general")
            scheduler._maybe_show(now + 10 * 60)
            self.assertEqual(shown[0]["kind"], "general")
            self.assertEqual(shown[0]["combined"], ["general", "eyes"])
            self.assertFalse(any(step.startswith("For the eyes:") for step in shown[0]["steps"]))
            self.assertEqual(shown[0]["duration_seconds"], 5 * 60)
        finally:
            MODULE.pause_media_players = original_pause
            db.close()

    def test_manual_quick_start_bypasses_activity_rotation_wait(self):
        config = MODULE.Config()
        db = MODULE.UsageDatabase(Path(TMP.name) / "manual_fair_reminder_order.sqlite3")
        shown = []
        scheduler = MODULE.Scheduler(config, db, shown.append)
        original_pause = MODULE.pause_media_players
        MODULE.pause_media_players = lambda: []
        try:
            scheduler.state["last_completed_kind"] = "eyes"
            scheduler.state["accrued"]["general"] = scheduler._target_seconds("general") - 5 * 60
            scheduler.trigger("eyes")
            self.assertEqual(shown[0]["kind"], "eyes")
        finally:
            MODULE.pause_media_players = original_pause
            db.close()

    def test_rotating_routines_have_variety(self):
        expected = {"eyes": 3, "general": 12, "neck": 6, "back": 5, "wrists": 5, "breathing": 5}
        for kind, count in expected.items():
            variants = MODULE.REMINDER_META[kind]["variants"]
            self.assertEqual(len(variants), count, kind)
            self.assertEqual(len({variant["title"] for variant in variants}), count, kind)
            self.assertTrue(
                all(variant["steps"] and variant["duration_seconds"] for variant in variants), kind
            )

    def test_open_reminder_pauses_screen_time(self):
        config = MODULE.Config()
        db = MODULE.UsageDatabase(Path(TMP.name) / "break_pause.sqlite3")
        scheduler = MODULE.Scheduler(config, db, lambda _payload: None)
        scheduler.read_activity = lambda: MODULE.Activity(True, "test.app", "Test")
        scheduler._active_kind = "eyes"
        scheduler._last_tick = MODULE.time.monotonic() - 5
        scheduler.tick()
        self.assertEqual(db.total_for_day(), 0)

    def test_manual_pause_keeps_screen_time_but_stops_reminder_clock(self):
        config = MODULE.Config()
        config.data["manual_pause"] = True
        db = MODULE.UsageDatabase(Path(TMP.name) / "manual_pause.sqlite3")
        scheduler = MODULE.Scheduler(config, db, lambda _payload: None)
        scheduler.read_activity = lambda: MODULE.Activity(True, "test.app", "Test")
        scheduler._last_tick = MODULE.time.monotonic() - 5
        scheduler.tick()
        self.assertGreaterEqual(db.total_for_day(), 4.5)
        self.assertEqual(scheduler.state["accrued"]["eyes"], 0)

    def test_screen_share_keeps_screen_time_but_stops_reminder_clock(self):
        config = MODULE.Config()
        config.data["pause_on_screen_share"] = True
        db = MODULE.UsageDatabase(Path(TMP.name) / "screen_share.sqlite3")
        scheduler = MODULE.Scheduler(config, db, lambda _payload: None)
        scheduler.read_activity = lambda: MODULE.Activity(True, "meeting.app", "Meeting", False, True)
        scheduler._last_tick = MODULE.time.monotonic() - 5
        scheduler.tick()
        self.assertGreaterEqual(db.total_for_day(), 4.5)
        self.assertEqual(scheduler.state["accrued"]["eyes"], 0)

    def test_screen_share_closes_an_already_open_reminder(self):
        config = MODULE.Config()
        config.data["pause_on_screen_share"] = True
        db = MODULE.UsageDatabase(Path(TMP.name) / "screen_share_open.sqlite3")
        scheduler = MODULE.Scheduler(config, db, lambda _payload: None)
        scheduler._active_kind = "eyes"
        scheduler.state["active_id"] = "open-eyes"
        scheduler.read_activity = lambda: MODULE.Activity(True, "meeting.app", "Meeting", False, True)
        scheduler.tick()
        self.assertIsNone(scheduler._active_kind)
        self.assertIsNone(scheduler.state["active_id"])
        self.assertGreater(scheduler.state["snooze_until"]["eyes"], MODULE.time.time())

    def test_accessible_app_names_are_normalized(self):
        config = MODULE.Config()
        db = MODULE.UsageDatabase(Path(TMP.name) / "atspi.sqlite3")
        scheduler = MODULE.Scheduler(config, db, lambda _payload: None)
        chrome = SimpleNamespace(get_name=lambda: "Google Chrome", get_process_id=lambda: 0)
        code = SimpleNamespace(get_name=lambda: "Visual Studio Code", get_process_id=lambda: 0)
        short_code = SimpleNamespace(get_name=lambda: "code", get_process_id=lambda: 0)
        self.assertEqual(
            scheduler._resolve_accessible_app(chrome), ("google-chrome.desktop", "Google Chrome")
        )
        self.assertEqual(scheduler._resolve_accessible_app(code), ("code_code.desktop", "Visual Studio Code"))
        self.assertEqual(
            scheduler._resolve_accessible_app(short_code), ("code_code.desktop", "Visual Studio Code")
        )

    def test_atspi_gap_reuses_last_real_application(self):
        config = MODULE.Config()
        db = MODULE.UsageDatabase(Path(TMP.name) / "atspi_cache.sqlite3")
        scheduler = MODULE.Scheduler(config, db, lambda _payload: None)
        scheduler._last_accessible_activity = MODULE.Activity(True, "google-chrome.desktop", "Google Chrome")
        scheduler._atspi_activity = lambda: None
        scheduler._screen_sharing_atspi = lambda: False
        scheduler._fallback_idle_ms = lambda: 0
        activity = scheduler.read_activity()
        self.assertEqual(activity.app_id, "google-chrome.desktop")
        self.assertEqual(scheduler.activity_source, "atspi-cache")

    def test_settings_frequency_methods_persist_values(self):
        config = MODULE.Config()
        dummy = SimpleNamespace(app=SimpleNamespace(config=config), refresh=lambda: None)
        MODULE.MainWindow._set_reminder_frequency(dummy, "eyes", 25)
        MODULE.MainWindow._set_reminder_frequency(dummy, "drops", 3)
        MODULE.MainWindow._set_idle_value(dummy, 90)
        MODULE.MainWindow._set_snooze_value(dummy, 12)
        MODULE.MainWindow._set_reminder_duration(dummy, "eyes", 80)
        MODULE.MainWindow._set_reminder_duration(dummy, "neck", 240)
        MODULE.MainWindow._set_reminder_duration(dummy, "drops", 999)
        saved = MODULE.load_json(MODULE.CONFIG_FILE, {})
        self.assertEqual(saved["reminders"]["eyes"]["interval_minutes"], 25)
        self.assertEqual(saved["reminders"]["drops"]["times_per_day"], 3)
        self.assertEqual(saved["idle_threshold_seconds"], 90)
        self.assertEqual(saved["snooze_minutes"], 12)
        self.assertEqual(saved["reminders"]["eyes"]["duration_seconds"], 80)
        self.assertEqual(saved["reminders"]["neck"]["duration_seconds"], 240)
        self.assertEqual(saved["reminders"]["drops"]["duration_seconds"], 60)
        self.assertEqual(MODULE.CUSTOM_DURATION_LIMITS["eyes"], (20, 120, 10))

    def test_english_is_default_and_formats_are_localized(self):
        config = MODULE.Config()
        self.assertEqual(config.data["language"], "en")
        self.assertEqual(MODULE.format_duration(90, "en"), "1 min")
        self.assertEqual(MODULE.format_precise_duration(90, "en"), "1 min 30 sec")
        self.assertEqual(MODULE.snooze_button_text(1), "Напомнить через 1 минуту")
        self.assertEqual(MODULE.snooze_button_text(4), "Напомнить через 4 минуты")
        self.assertEqual(MODULE.snooze_button_text(20, "en"), "Remind me in 20 min")

    def test_wellness_checkins_persist_and_join_daily_context(self):
        db = MODULE.UsageDatabase(Path(TMP.name) / "wellness.sqlite3")
        now = MODULE.time.time()
        db.save_wellness(3, 4, 2, 5, now)
        db.save_wellness(5, 5, 4, 6, now - 86400)
        db.record_tick(now, "browser.desktop", "Browser", 7)
        db.log_reminder("eyes", "done", now, 20)
        latest = db.latest_wellness()
        self.assertEqual((latest["headache"], latest["eyes"], latest["neck"], latest["back"]), (3, 4, 2, 5))
        today = db.wellness_days(7)[-1]
        self.assertEqual(today["checkins"], 1)
        self.assertEqual(today["breaks"], 1)
        self.assertEqual(today["screen_seconds"], 7)
        day = MODULE.datetime.fromtimestamp(now).date().isoformat()
        self.assertEqual(db.latest_wellness_for_day(day)["headache"], 3)
        self.assertEqual(db.exercise_overview_for_day(day)["done"], 1)
        current, previous = db.wellness_comparison(day)
        self.assertIsNotNone(current)
        self.assertIsNotNone(previous)
        self.assertEqual(previous["headache"], 5)
        period = db.wellness_period_summary(30)
        self.assertEqual(period["recorded_days"], 2)
        self.assertEqual(db.total_for_period(30), 7)
        yesterday = (MODULE.datetime.fromtimestamp(now).date() - MODULE.timedelta(days=1)).isoformat()
        selected = db.wellness_summary_between(yesterday, day)
        self.assertEqual(selected["recorded_days"], 2)
        self.assertEqual(selected["headache"], 4)
        self.assertEqual(db.total_between(yesterday, day), 7)
        self.assertEqual(db.exercise_overview_between(yesterday, day)["done"], 1)
        range_current, range_previous = db.wellness_range_comparison(
            MODULE.datetime.fromtimestamp(now).date(), MODULE.datetime.fromtimestamp(now).date()
        )
        self.assertEqual(range_current["headache"], 3)
        self.assertEqual(range_previous["headache"], 5)

    def test_backup_restores_analytics_tables(self):
        source = MODULE.UsageDatabase(Path(TMP.name) / "backup_source.sqlite3")
        now = MODULE.time.time()
        source.record_tick(now, "browser.desktop", "Browser", 7)
        source.log_reminder("eyes", "done", now, 20)
        source.save_wellness(3, 4, 2, 5, now)
        tables = source.backup_tables()
        self.assertEqual(
            set(tables),
            {
                "daily_app",
                "usage_segments",
                "reminder_events",
                "wellness_checkins",
                "habit_events",
                "app_notifications",
                "achievement_unlocks",
                "training_enrollments",
                "training_events",
            },
        )

        restored = MODULE.UsageDatabase(Path(TMP.name) / "backup_restored.sqlite3")
        restored.record_tick(now, "other.desktop", "Other", 3)
        restored.restore_tables(tables)
        self.assertEqual(restored.total_for_day(), 7)
        self.assertEqual(restored.top_apps(7)[0]["app_name"], "Browser")
        self.assertEqual(restored.exercise_overview(7)["done"], 1)
        self.assertEqual(restored.latest_wellness()["back"], 5)

    def test_training_courses_balance_work_and_recovery(self):
        self.assertEqual(MODULE.COURSE_DURATIONS, (7, 30, 180, 360))
        self.assertEqual(
            set(MODULE.COURSES),
            {"full_body", "upper_body", "legs", "lower_body", "balance"},
        )
        for course_id, course in MODULE.COURSES.items():
            self.assertIn(course["icon"], MODULE.REMINDER_META, course_id)
            for days_per_week in (2, 3, 4, 5):
                week = [
                    MODULE.training_day(
                        course_id,
                        day,
                        7,
                        days_per_week=days_per_week,
                    )
                    for day in range(1, 8)
                ]
                kinds = [plan["kind"] for plan in week]
                self.assertEqual(
                    sum(kind != "rest" for kind in kinds),
                    days_per_week,
                    (course_id, days_per_week),
                )
                self.assertEqual(kinds.count("strength"), 3 if days_per_week >= 3 else 2)
                self.assertFalse(
                    any(left == right == "strength" for left, right in zip(kinds, kinds[1:], strict=False)),
                    (course_id, days_per_week),
                )

            custom_days = (1, 3, 6)
            custom_week = MODULE.weekly_pattern(3, weekdays=custom_days)
            self.assertEqual(
                tuple(index for index, (kind, _session) in enumerate(custom_week) if kind != "rest"),
                custom_days,
                course_id,
            )

            lighter = MODULE.training_day(course_id, 28, 360)
            self.assertTrue(lighter["lighter"], course_id)
            self.assertLessEqual(lighter["rounds"], 2, course_id)
            maintained = MODULE.training_day(course_id, 120, 360)
            last = MODULE.training_day(course_id, 351, 360)
            self.assertEqual(maintained["phase"], last["phase"], course_id)
            self.assertTrue(
                all(
                    earlier["target_value"] <= later["target_value"]
                    for earlier, later in zip(maintained["exercises"], last["exercises"], strict=True)
                ),
                course_id,
            )

    def test_training_levels_and_guided_stages(self):
        beginner = MODULE.training_day("full_body", 57, 180, fitness_level="beginner")
        regular = MODULE.training_day("full_body", 57, 180, fitness_level="regular")
        trained = MODULE.training_day("full_body", 57, 180, fitness_level="trained")
        advanced = MODULE.training_day("full_body", 57, 180, fitness_level="advanced")
        self.assertEqual(len(MODULE.FITNESS_LEVELS), 4)
        self.assertEqual(beginner["rounds"], 1)
        self.assertLessEqual(regular["rounds"], trained["rounds"])
        self.assertLessEqual(trained["rounds"], advanced["rounds"])
        self.assertLessEqual(advanced["rounds"], 3)
        self.assertLess(len(beginner["exercises"]), len(advanced["exercises"]))
        for low, high in zip(beginner["exercises"], advanced["exercises"], strict=False):
            self.assertLessEqual(low["target_value"], high["target_value"])
            self.assertTrue(low["image"].startswith("training-"))

        shoulder_beginner = MODULE.training_day("upper_body", 1, 30, fitness_level="beginner")
        shoulder_regular = MODULE.training_day("upper_body", 3, 30, fitness_level="regular")
        shoulder_trained = MODULE.training_day("upper_body", 1, 30, fitness_level="trained")
        self.assertNotIn("chair_dip", [item["id"] for item in shoulder_beginner["exercises"]])
        self.assertIn("floor_pushup", [item["id"] for item in shoulder_regular["exercises"]])
        self.assertIn("chair_dip", [item["id"] for item in shoulder_trained["exercises"]])

        lower_beginner = MODULE.training_day("lower_body", 1, 30, fitness_level="beginner")
        lower_regular = MODULE.training_day("lower_body", 1, 30, fitness_level="regular")
        self.assertNotIn(
            "supported_split_squat",
            [item["id"] for item in lower_beginner["exercises"]],
        )
        self.assertIn(
            "supported_split_squat",
            [item["id"] for item in lower_regular["exercises"]],
        )

        stages = MODULE.training_stages(regular)
        exercises = [item for item in stages if item["type"] == "exercise"]
        rests = [item for item in stages if item["type"] == "rest"]
        self.assertEqual(len(rests), len(exercises) - 1)
        self.assertEqual(stages[-1]["type"], "recovery")
        self.assertTrue(any(item["timed"] for item in exercises))
        self.assertTrue(any(not item["timed"] for item in exercises))

    def test_training_runner_done_advances_timed_and_repetition_stages(self):
        for timed in (True, False):
            advanced = []
            runner = SimpleNamespace(
                completed=False,
                running=True,
                stage_index=0,
                _current=lambda value=timed: {"type": "exercise", "timed": value},
                _advance=lambda target=advanced: target.append(True),
            )
            MODULE.TrainingSessionOverlay._primary_clicked(runner, None)
            self.assertEqual(advanced, [True])

        paused = SimpleNamespace(
            completed=False,
            running=False,
            stage_index=0,
            _current=lambda: {"type": "exercise", "timed": True},
            _advance=lambda: self.fail("a paused workout must not advance"),
        )
        MODULE.TrainingSessionOverlay._primary_clicked(paused, None)

        source = (Path(__file__).parents[1] / "healthbreak.py").read_text()
        runner_source = source.split("class TrainingSessionOverlay", 1)[1].split("class FallbackOverlay", 1)[
            0
        ]
        self.assertNotIn("pause_media_players()", runner_source)
        self.assertIn("content.set_vexpand(True)", runner_source)
        self.assertIn("actions.set_valign(Gtk.Align.END)", runner_source)
        self.assertIn("self.pause_button.set_size_request(170, 46)", runner_source)
        self.assertIn("self.primary_button.set_size_request(220, 46)", runner_source)
        self.assertIn("content_scroll.set_child(content)", runner_source)
        self.assertNotIn("runner_scroll.set_child(clamp)", runner_source)

        css = (Path(__file__).parents[1] / "assets" / "style.css").read_text()
        self.assertIn(".training-active-hero-flow flowboxchild {\n  /*", css)
        self.assertIn("min-width: 380px;", css)
        self.assertIn(".training-days-flow flowboxchild { min-width: 84px; }", css)

    def test_course_selection_returns_training_page_to_the_top(self):
        values = []
        adjustment = SimpleNamespace(
            get_lower=lambda: 0.0,
            set_value=values.append,
        )
        window = SimpleNamespace(training_scroller=SimpleNamespace(get_vadjustment=lambda: adjustment))
        result = MODULE.MainWindow._scroll_training_to_top(window)
        self.assertEqual(values, [0.0])
        self.assertEqual(result, MODULE.GLib.SOURCE_REMOVE)

        source = (Path(__file__).parents[1] / "healthbreak.py").read_text()
        self.assertGreaterEqual(source.count("self._rebuild_active_training_at_top()"), 5)
        self.assertIn("GLib.idle_add(self._finish_opening_active_training)", source)
        self.assertIn("self.training_scroller = page.get_child()", source)

    def test_training_setup_uses_answers_to_recommend_one_course(self):
        source = (Path(__file__).parents[1] / "healthbreak.py").read_text()
        self.assertIn('self.training_setup_step = 0', source)
        self.assertIn('self.training_view = "active" if active_training else "setup"', source)
        self.assertIn('self._training_answer_options(', source)
        self.assertIn('recommendation = self._training_recommendation_card()', source)
        self.assertIn('"Your recommended plan"', source)
        self.assertNotIn('training_course_choice_buttons', source)
        self.assertNotIn('"Choose one course"', source)
        self.assertIn('label="Change course" if self.language == "en" else "Сменить курс"', source)
        self.assertIn('self._training_setup_progress()', source)

        answers = SimpleNamespace(training_goal_choice="balanced", training_style_choice="steady")
        self.assertEqual(MODULE.MainWindow._recommended_training_course(answers), "full_body")
        answers.training_goal_choice = "upper"
        self.assertEqual(MODULE.MainWindow._recommended_training_course(answers), "upper_body")
        answers.training_goal_choice = "mobility"
        self.assertEqual(MODULE.MainWindow._recommended_training_course(answers), "balance")
        answers.training_goal_choice = "lower"
        answers.training_style_choice = "gentle"
        self.assertEqual(MODULE.MainWindow._recommended_training_course(answers), "legs")
        answers.training_style_choice = "strength"
        self.assertEqual(MODULE.MainWindow._recommended_training_course(answers), "lower_body")

        opened = []
        started = []
        window = SimpleNamespace(
            app=SimpleNamespace(db=SimpleNamespace(active_training=lambda: {"course_id": "full_body"})),
            training_course_choice="full_body",
            _rebuild_active_training_at_top=lambda: opened.append(True),
            _start_training_course=lambda _button, course_id: started.append(course_id),
        )
        MODULE.MainWindow._finish_training_setup(window, None)
        self.assertEqual(opened, [True])
        self.assertEqual(started, [])

        window.training_course_choice = "upper_body"
        MODULE.MainWindow._finish_training_setup(window, None)
        self.assertEqual(started, ["upper_body"])

    def test_training_reset_reopens_active_course_after_dialog_settles(self):
        rebuilds = []
        scrolls = []

        class Stack:
            visible = "training"

            def get_visible_child_name(self):
                return self.visible

            def set_visible_child_name(self, name):
                self.visible = name

        window = SimpleNamespace(
            app=SimpleNamespace(db=SimpleNamespace(active_training=lambda: object())),
            stack=Stack(),
            training_view="catalog",
            _rebuild_training=lambda: rebuilds.append("active"),
            _scroll_training_to_top=lambda: scrolls.append(0),
        )
        result = MODULE.MainWindow._finish_opening_active_training(window)
        self.assertEqual(window.training_view, "active")
        self.assertEqual(window.stack.visible, "training")
        self.assertEqual(rebuilds, ["active"])
        self.assertEqual(scrolls, [0])
        self.assertEqual(result, MODULE.GLib.SOURCE_REMOVE)

    def test_sidebar_navigation_has_group_dividers(self):
        css = (Path(__file__).parents[1] / "assets" / "style.css").read_text()
        self.assertIn(".sidebar stacksidebar row:nth-child(2)", css)
        self.assertIn(".sidebar stacksidebar row:nth-child(5)", css)
        self.assertIn(".sidebar stacksidebar row:nth-child(7)", css)

    def test_strength_days_progress_until_the_planned_lighter_week(self):
        for course_id in MODULE.COURSES:
            first = MODULE.training_day(course_id, 1, 180, fitness_level="regular")
            third = MODULE.training_day(course_id, 5, 180, fitness_level="regular")
            next_week = MODULE.training_day(course_id, 8, 180, fitness_level="regular")
            self.assertEqual(
                (first["build_step"], third["build_step"], next_week["build_step"]),
                (0, 2, 3),
                course_id,
            )

            first_targets = {
                item["id"]: item["target_value"] for item in first["exercises"] if item["id"] != "room_warmup"
            }
            third_targets = {
                item["id"]: item["target_value"] for item in third["exercises"] if item["id"] != "room_warmup"
            }
            for exercise_id, target in first_targets.items():
                self.assertEqual(third_targets[exercise_id], target + 2, course_id)

            first_warmup = next(item for item in first["exercises"] if item["id"] == "room_warmup")
            third_warmup = next(item for item in third["exercises"] if item["id"] == "room_warmup")
            self.assertEqual(first_warmup["target_value"], third_warmup["target_value"])

        lighter = MODULE.training_day("full_body", 22, 180, fitness_level="regular")
        self.assertTrue(lighter["lighter"])
        self.assertEqual(lighter["build_step"], 0)

    def test_new_or_reset_course_starts_with_a_workout_on_an_off_day(self):
        saturday = MODULE.datetime(2026, 7, 18, 12, 0)
        database = MODULE.UsageDatabase(Path(TMP.name) / "training-reset-start.sqlite3")
        enrollment = database.start_training(
            "full_body",
            30,
            "beginner",
            weekdays=(0, 2, 4),
            now=saturday.timestamp(),
        )
        reset = database.reset_training(int(enrollment["id"]), now=saturday.timestamp())
        plan = MODULE.training_day(
            str(reset["course_id"]),
            int(reset["current_day"]),
            int(reset["duration_days"]),
            "en",
            str(reset["fitness_level"]),
            int(reset["days_per_week"]),
            json.loads(str(reset["weekdays"])),
            saturday.weekday(),
        )
        self.assertEqual(plan["kind"], "strength")
        self.assertEqual(plan["session_key"], "a")
        self.assertTrue(plan["exercises"])

    def test_training_uses_packaged_photos_and_no_workout_equipment(self):
        forbidden = (
            "bottle",
            "dumbbell",
            "weight plate",
            "гантел",
            "бутыл",
            "walk",
            "ходьб",
            "пройд",
        )
        referenced = set()
        for exercise_id, exercise in TRAINING.EXERCISES.items():
            image = str(exercise["image"])
            referenced.add(image)
            self.assertTrue((MODULE.ROOT / "assets" / image).is_file(), exercise_id)
            copy = " ".join(
                str(exercise[key]).lower() for key in ("instruction_en", "instruction_ru", "cue_en", "cue_ru")
            )
            self.assertFalse(any(term in copy for term in forbidden), exercise_id)
        for course_id, course in MODULE.COURSES.items():
            image = str(course["image"])
            referenced.add(image)
            self.assertTrue((MODULE.ROOT / "assets" / image).is_file(), course_id)
            equipment = f"{course['equipment_en']} {course['equipment_ru']}".lower()
            self.assertFalse(any(term in equipment for term in forbidden), course_id)
        self.assertGreaterEqual(len(referenced), 18)

    def test_training_switch_resume_reset_and_calendar_history(self):
        database = MODULE.UsageDatabase(Path(TMP.name) / "training-switch.sqlite3")
        started = MODULE.time.time() - 3 * 86400
        first = database.start_training(
            "core",
            30,
            "regular",
            3,
            now=started,
            weekdays=(1, 3, 6),
        )
        first_id = int(first["id"])
        self.assertEqual(json.loads(first["weekdays"]), [1, 3, 6])
        database.complete_training_day(first_id, 1, "a", 300, now=started)

        database.start_training("upper_body", 7, "beginner", 2, now=started + 86400)
        self.assertEqual(database.active_training()["course_id"], "upper_body")
        saved_first = database.resumable_training("core")
        self.assertIsNotNone(saved_first)
        self.assertEqual(saved_first["current_day"], 2)

        database.resume_training(first_id)
        resumed = database.active_training()
        self.assertEqual(resumed["course_id"], "full_body")
        self.assertEqual(resumed["fitness_level"], "regular")
        self.assertEqual(resumed["days_per_week"], 3)
        self.assertEqual(json.loads(resumed["weekdays"]), [1, 3, 6])
        updated = database.update_training_weekdays(first_id, (0, 3, 5))
        self.assertEqual(updated["current_day"], 2)
        self.assertEqual(updated["days_per_week"], 3)
        self.assertEqual(json.loads(updated["weekdays"]), [0, 3, 5])
        self.assertEqual(database.training_summary(first_id)["completed_days"], 1)
        updated = database.update_training_plan(first_id, fitness_level="trained")
        self.assertEqual(updated["fitness_level"], "trained")
        self.assertEqual(updated["current_day"], 2)
        self.assertEqual(database.training_summary(first_id)["completed_days"], 1)
        with self.assertRaises(ValueError):
            database.update_training_weekdays(first_id, (0,))
        calendar_rows = database.training_calendar(
            MODULE.datetime.fromtimestamp(started).date() - MODULE.timedelta(days=1),
            MODULE.datetime.fromtimestamp(started).date() + MODULE.timedelta(days=1),
        )
        self.assertEqual(len(calendar_rows), 1)
        self.assertEqual(calendar_rows[0]["course_id"], "full_body")

        reset = database.reset_training(
            first_id,
            duration_days=180,
            fitness_level="advanced",
            weekdays=(0, 1, 3, 5),
            now=started + 2 * 86400,
        )
        self.assertEqual(reset["current_day"], 1)
        self.assertEqual(reset["duration_days"], 180)
        self.assertEqual(reset["fitness_level"], "advanced")
        self.assertEqual(reset["days_per_week"], 4)
        self.assertEqual(json.loads(reset["weekdays"]), [0, 1, 3, 5])
        self.assertEqual(database.training_summary(first_id)["completed_days"], 0)
        self.assertEqual(database.training_history()[1]["course_id"], "upper_body")

    def test_legacy_training_courses_migrate_without_losing_progress(self):
        path = Path(TMP.name) / "training-legacy.sqlite3"
        database = MODULE.UsageDatabase(path)
        started = MODULE.time.time() - 86400
        with database.conn:
            cursor = database.conn.execute(
                """INSERT INTO training_enrollments
                   (course_id, duration_days, fitness_level, days_per_week, weekdays,
                    started_at, current_day, is_active)
                   VALUES('shoulders',30,'regular',3,'[0,2,4]',?,4,1)""",
                (started,),
            )
            database.conn.execute(
                """INSERT INTO training_events
                   (enrollment_id, created_at, course_day, session_key, duration_seconds)
                   VALUES(?,?,3,'a',420)""",
                (int(cursor.lastrowid), started),
            )
        database.close()

        migrated = MODULE.UsageDatabase(path)
        active = migrated.active_training()
        self.assertEqual(active["course_id"], "upper_body")
        self.assertEqual(active["current_day"], 4)
        self.assertEqual(migrated.training_summary(int(active["id"]))["completed_days"], 1)

    def test_training_progress_is_daily_and_survives_backup(self):
        source = MODULE.UsageDatabase(Path(TMP.name) / "training-source.sqlite3")
        now = MODULE.time.time()
        enrollment = source.start_training("full_body", 30, now=now)
        enrollment_id = int(enrollment["id"])
        self.assertEqual(source.active_training()["current_day"], 1)
        self.assertFalse(source.complete_training_day(enrollment_id, 1, "a", 420, now=now))
        self.assertFalse(source.training_available_today(enrollment_id, now=now))
        with self.assertRaises(ValueError):
            source.complete_training_day(enrollment_id, 2, "recovery", 240, now=now + 60)
        self.assertFalse(source.complete_training_day(enrollment_id, 2, "recovery", 240, now=now + 86400))
        self.assertEqual(source.active_training()["current_day"], 3)
        self.assertEqual(source.training_summary(enrollment_id)["completed_days"], 2)

        restored = MODULE.UsageDatabase(Path(TMP.name) / "training-restored.sqlite3")
        restored.restore_tables(source.backup_tables())
        self.assertEqual(restored.active_training()["course_id"], "full_body")
        self.assertEqual(restored.active_training()["current_day"], 3)
        self.assertEqual(restored.active_training()["weekdays"], "[0,2,4]")
        self.assertEqual(restored.training_summary()["duration_seconds"], 660)

    def test_multilevel_achievements_unlock_once_and_restore(self):
        self.assertGreaterEqual(len(MODULE.ACHIEVEMENTS), 35)
        self.assertGreaterEqual(
            max(item["level"] for item in MODULE.ACHIEVEMENTS if item["series"] == "rhythm"),
            7,
        )
        self.assertEqual(
            max(item["target"] for item in MODULE.ACHIEVEMENTS if item["series"] == "rhythm"),
            1000,
        )
        self.assertEqual(MODULE.achievement_level_mark(7), "VII")
        achievement = {"level": 2, "title_en": "Work rhythm", "title_ru": "Рабочий ритм"}
        self.assertEqual(
            MODULE.achievement_unlock_body(achievement, "en"),
            "You reached Level II in Work rhythm.",
        )
        self.assertEqual(
            MODULE.achievement_unlock_body(achievement, "ru"),
            "Открыт уровень II в серии «Рабочий ритм».",
        )
        self.assertNotIn("·", MODULE.achievement_unlock_body(achievement, "en"))
        self.assertEqual(
            MODULE.notification_body_for_display("achievement", "Work rhythm · II", "en"),
            "You reached Level II in Work rhythm.",
        )
        self.assertEqual(
            MODULE.notification_body_for_display("habit", "Walk · now", "en"),
            "Walk · now",
        )
        source = MODULE.UsageDatabase(Path(TMP.name) / "achievements.sqlite3")
        for offset in range(10):
            source.log_reminder("eyes", "done", now=MODULE.time.time() + offset, duration_seconds=20)
        unlocked = {item["id"] for item in source.evaluate_achievements(now=12345)}
        self.assertIn("rhythm-1", unlocked)
        self.assertIn("rhythm-10", unlocked)
        self.assertIn("eyes-5", unlocked)
        self.assertEqual(source.evaluate_achievements(now=12346), [])

        restored = MODULE.UsageDatabase(Path(TMP.name) / "achievements-restored.sqlite3")
        restored.restore_tables(source.backup_tables())
        restored_unlocks = {
            item["id"]: item["unlocked_at"]
            for item in restored.achievement_progress()
            if item["unlocked_at"] is not None
        }
        self.assertEqual(restored_unlocks["rhythm-10"], 12345)
        self.assertEqual(restored_unlocks["eyes-5"], 12345)

    def test_habits_and_notification_center_persist(self):
        db = MODULE.UsageDatabase(Path(TMP.name) / "habits.sqlite3")
        now = MODULE.time.time()
        db.log_habit("walk", now=now)
        db.log_habit("walk", now=now)
        self.assertEqual(db.habit_count("walk"), 2)
        db.log_habit("walk", -1, now=now)
        self.assertEqual(db.habit_count("walk"), 1)
        self.assertEqual(db.habit_week_count("walk"), 1)
        notification_id = db.add_notification("habit", "Walk", "Time to move", "habits", now=now)
        self.assertEqual(db.unread_notifications(), 1)
        self.assertEqual(db.notifications()[0]["id"], notification_id)
        db.mark_notifications_read()
        self.assertEqual(db.unread_notifications(), 0)

    def test_habit_reminder_fires_once_and_skips_completed_goal(self):
        config = MODULE.Config()
        now = MODULE.datetime.now()
        config.data["habits"] = [
            {
                "id": "test-habit",
                "title": "Test",
                "enabled": True,
                "target": 1,
                "reminder_enabled": True,
                "reminder_time": now.strftime("%H:%M"),
                "icon": "general",
            }
        ]
        db = MODULE.UsageDatabase(Path(TMP.name) / "habit_scheduler.sqlite3")
        prompted = []
        scheduler = MODULE.Scheduler(
            config, db, lambda _payload: None, prompt_habit=lambda habit: prompted.append(habit["id"])
        )
        scheduler._maybe_prompt_habits()
        scheduler._maybe_prompt_habits()
        self.assertEqual(prompted, ["test-habit"])
        scheduler.state["habit_reminders_sent"] = []
        db.log_habit("test-habit")
        scheduler._maybe_prompt_habits()
        self.assertEqual(prompted, ["test-habit"])

    def test_training_reminders_follow_fixed_and_flexible_intervals(self):
        config = MODULE.Config()
        config.data["training_reminders_enabled"] = True
        db = MODULE.UsageDatabase(Path(TMP.name) / "training_reminders.sqlite3")
        base = MODULE.datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
        today = base.weekday()
        weekdays = tuple(sorted({today, (today + 2) % 7, (today + 4) % 7}))
        db.start_training("full_body", 30, "beginner", weekdays=weekdays, now=base.timestamp())
        prompts = []
        scheduler = MODULE.Scheduler(
            config,
            db,
            lambda _payload: None,
            prompt_training=lambda enrollment, plan, count: prompts.append(
                (int(enrollment["id"]), plan["kind"], count)
            ),
        )

        config.data["training_reminder_time"] = "11:59"
        scheduler.reset_training_reminders(base.timestamp() - 3600)
        scheduler._maybe_prompt_training(base.timestamp())
        scheduler._maybe_prompt_training(base.timestamp() + 3599)
        scheduler._maybe_prompt_training(base.timestamp() + 3600)
        self.assertEqual([item[2] for item in prompts], [1, 2])

        prompts.clear()
        config.data["training_reminder_time"] = None
        scheduler.reset_training_reminders(base.timestamp())
        scheduler._maybe_prompt_training(base.timestamp() + 8999)
        scheduler._maybe_prompt_training(base.timestamp() + 9000)
        scheduler._maybe_prompt_training(base.timestamp() + 17999)
        scheduler._maybe_prompt_training(base.timestamp() + 18000)
        self.assertEqual([item[2] for item in prompts], [1, 2])

        config.data["training_reminders_enabled"] = False
        scheduler.reset_training_reminders(base.timestamp())
        scheduler._maybe_prompt_training(base.timestamp() + 20000)
        self.assertEqual([item[2] for item in prompts], [1, 2])

    def test_backup_payload_contains_settings_and_analytics(self):
        config = MODULE.Config()
        db = MODULE.UsageDatabase(Path(TMP.name) / "backup_payload.sqlite3")
        dummy = SimpleNamespace(app=SimpleNamespace(config=config, db=db))
        payload = MODULE.MainWindow._backup_payload(dummy)
        self.assertEqual(payload["format"], "zdorovo-backup")
        self.assertEqual(payload["settings"]["snooze_minutes"], config.data["snooze_minutes"])
        self.assertIn("daily_app", payload["analytics"])
        self.assertIn("achievement_unlocks", payload["analytics"])

    def test_reminder_actions_resume_only_players_paused_by_the_app(self):
        original_pause = MODULE.pause_media_players
        original_resume = MODULE.resume_media_players
        MODULE.pause_media_players = lambda: ["org.mpris.MediaPlayer2.test"]
        try:
            for action in ("done", "snooze"):
                with self.subTest(action=action):
                    config = MODULE.Config()
                    db = MODULE.UsageDatabase(Path(TMP.name) / f"resume_media_{action}.sqlite3")
                    shown = []
                    resumed = []
                    scheduler = MODULE.Scheduler(config, db, shown.append)

                    def record_resume(players, target=resumed):
                        target.extend(players)
                        return len(players)

                    MODULE.resume_media_players = record_resume
                    scheduler.trigger("eyes")
                    MODULE.atomic_json(
                        MODULE.RESPONSE_FILE,
                        {"id": shown[0]["id"], "action": action},
                    )
                    scheduler._consume_response()
                    scheduler.resume_paused_media()
                    self.assertEqual(resumed, ["org.mpris.MediaPlayer2.test"])
                    db.close()
        finally:
            MODULE.pause_media_players = original_pause
            MODULE.resume_media_players = original_resume

    def test_wellness_prompt_is_spaced_and_stops_after_checkin(self):
        config = MODULE.Config()
        db = MODULE.UsageDatabase(Path(TMP.name) / "wellness_prompt.sqlite3")
        prompts = []
        scheduler = MODULE.Scheduler(
            config, db, lambda _payload: None, prompt_wellness=lambda: prompts.append(1)
        )
        scheduler.state["wellness_active_seconds"] = 30 * 60
        scheduler._maybe_prompt_wellness()
        scheduler._maybe_prompt_wellness()
        self.assertEqual(len(prompts), 1)
        scheduler.state["wellness_active_seconds"] = 3 * 3600
        scheduler._maybe_prompt_wellness()
        self.assertEqual(len(prompts), 2)
        db.save_wellness(2, 3, 1, 4)
        scheduler.state["wellness_active_seconds"] = 7 * 3600
        scheduler._maybe_prompt_wellness()
        self.assertEqual(len(prompts), 2)

    def test_wellness_prompts_can_be_disabled(self):
        config = MODULE.Config()
        config.data["wellness_reminders_enabled"] = False
        db = MODULE.UsageDatabase(Path(TMP.name) / "wellness_prompt_disabled.sqlite3")
        prompts = []
        scheduler = MODULE.Scheduler(
            config, db, lambda _payload: None, prompt_wellness=lambda: prompts.append(1)
        )
        scheduler.state["wellness_active_seconds"] = 8 * 3600
        scheduler._maybe_prompt_wellness()
        self.assertEqual(prompts, [])
        self.assertEqual(scheduler.state["wellness_prompt_count"], 0)

        config.data["wellness_reminders_enabled"] = True
        config.data["wellness_checkin_enabled"] = False
        scheduler.state["wellness_active_seconds"] = 8 * 3600
        scheduler._maybe_prompt_wellness()
        self.assertEqual(prompts, [])
        self.assertEqual(scheduler.state["wellness_prompt_count"], 0)


if __name__ == "__main__":
    unittest.main()
