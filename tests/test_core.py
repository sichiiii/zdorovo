import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

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
        expected = {"eyes": 3, "general": 6, "neck": 6, "back": 5, "wrists": 5, "breathing": 5}
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
            },
        )

        restored = MODULE.UsageDatabase(Path(TMP.name) / "backup_restored.sqlite3")
        restored.record_tick(now, "other.desktop", "Other", 3)
        restored.restore_tables(tables)
        self.assertEqual(restored.total_for_day(), 7)
        self.assertEqual(restored.top_apps(7)[0]["app_name"], "Browser")
        self.assertEqual(restored.exercise_overview(7)["done"], 1)
        self.assertEqual(restored.latest_wellness()["back"], 5)

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
