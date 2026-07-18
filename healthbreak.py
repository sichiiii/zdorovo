#!/usr/bin/env python3
"""Здорово — private break reminders and screen-time analytics for GNOME."""

from __future__ import annotations

import argparse
import calendar as pycalendar
import colorsys
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gi

from localization import reminder_meta as localized_reminder_meta
from localization import text as localized_text
from training import (
    COURSE_ALIASES,
    COURSE_DURATIONS,
    COURSES,
    FITNESS_LEVELS,
    normalize_course_id,
    normalize_weekdays,
    training_day,
    training_stages,
    upcoming_days,
    weekly_pattern,
)
from training import copy as training_copy

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Atspi", "2.0")
gi.require_version("GioUnix", "2.0")
gi.require_version("Graphene", "1.0")
gi.require_foreign("cairo")
from gi.repository import Adw, Atspi, Gdk, Gio, GioUnix, GLib, Graphene, Gtk  # noqa: E402

APP_ID = "io.github.jabka.Zdorovo"
APP_ICON_NAME = f"{APP_ID}-mint-v2"
APP_NAME = "Здорово"
APP_VERSION = "0.1.7"
ROOT = Path(__file__).resolve().parent
ASSET_ROOT = ROOT / "assets"
if not ASSET_ROOT.is_dir():
    ASSET_ROOT = Path("/usr/share/zdorovo/assets")
CONFIG_HOME = Path(os.environ.get("ZDOROVO_CONFIG_HOME", Path.home() / ".config" / "zdorovo"))
DATA_HOME = Path(os.environ.get("ZDOROVO_DATA_HOME", Path.home() / ".local" / "share" / "zdorovo"))
CONFIG_FILE = CONFIG_HOME / "config.json"
STATE_FILE = DATA_HOME / "scheduler-state.json"
ACTIVITY_FILE = DATA_HOME / "activity.json"
REMINDER_FILE = DATA_HOME / "reminder.json"
RESPONSE_FILE = DATA_HOME / "response.json"
DB_FILE = DATA_HOME / "usage.sqlite3"


DEFAULT_CONFIG: dict[str, Any] = {
    "language": "en",
    "language_selected": False,
    "dark_mode": False,
    "theme_mode": "light",
    "color_theme": "teal",
    "sidebar_collapsed": False,
    "theme_light_time": "07:00",
    "theme_dark_time": "21:00",
    "manual_pause": False,
    "analytics_hidden_apps": [],
    "guided_sound_enabled": True,
    "guided_sound_volume": -8.0,
    "snooze_minutes": 5,
    "training_duration_days": 30,
    "training_fitness_level": "beginner",
    "training_days_per_week": 3,
    "training_weekdays": [0, 2, 4],
    "training_reminders_enabled": True,
    "training_reminder_time": None,
    "wellness_checkin_enabled": True,
    "wellness_reminders_enabled": True,
    "notification_center_initialized": False,
    "pause_on_screen_share": True,
    "pause_on_fullscreen": False,
    "idle_threshold_seconds": 60,
    "habits": [
        {
            "id": "daily-movement",
            "title": "Прогулка или движение",
            "enabled": True,
            "target": 1,
            "reminder_enabled": True,
            "reminder_time": "18:00",
            "icon": "general",
        },
        {
            "id": "breathing-pause",
            "title": "Дыхательная пауза",
            "enabled": True,
            "target": 1,
            "reminder_enabled": False,
            "reminder_time": "16:00",
            "icon": "breathing",
        },
        {
            "id": "screen-free-evening",
            "title": "Время без экрана вечером",
            "enabled": False,
            "target": 1,
            "reminder_enabled": False,
            "reminder_time": "21:30",
            "icon": "eyes",
        },
    ],
    "reminders": {
        "eyes": {"enabled": True, "interval_minutes": 20, "duration_seconds": 20},
        "general": {"enabled": True, "interval_minutes": 50, "duration_seconds": 300},
        "neck": {"enabled": True, "interval_minutes": 180, "duration_seconds": 180},
        "drops": {"enabled": True, "times_per_day": 4, "duration_seconds": 60},
        "back": {"enabled": False, "interval_minutes": 120, "duration_seconds": 180},
        "wrists": {"enabled": False, "interval_minutes": 90, "duration_seconds": 90},
        "breathing": {"enabled": False, "interval_minutes": 120, "duration_seconds": 120},
        "water": {"enabled": False, "interval_minutes": 120, "duration_seconds": 30},
    },
}

COLOR_PALETTES: dict[str, dict[str, Any]] = {
    "teal": {
        "accent": (0.196, 0.498, 0.475),
        "accent_hex": "#327F79",
        "accent_light": (0.56, 0.84, 0.81),
        "backdrop_light": (0.933, 0.969, 0.965),
        "backdrop_dark": (0.075, 0.092, 0.091),
    },
    "burgundy": {
        "accent": (0.545, 0.227, 0.29),
        "accent_hex": "#8B3A4A",
        "accent_light": (0.89, 0.67, 0.72),
        "backdrop_light": (0.973, 0.945, 0.951),
        "backdrop_dark": (0.102, 0.073, 0.08),
    },
    "gray": {
        "accent": (0.39, 0.43, 0.47),
        "accent_hex": "#646E78",
        "accent_light": (0.76, 0.79, 0.82),
        "backdrop_light": (0.953, 0.958, 0.961),
        "backdrop_dark": (0.075, 0.078, 0.084),
    },
}

PALETTE_HEX_REPLACEMENTS: dict[str, dict[str, str]] = {
    "burgundy": {
        "#327F79": "#8B3A4A",
        "#246B66": "#70303D",
        "#2B756F": "#7C3443",
        "#4B9B94": "#A75B6A",
        "#9ED8D2": "#E3ADB8",
        "#B7E4DF": "#EAC2CA",
        "#C9EEEA": "#F0D4DA",
        "#C5EBE7": "#EDCDD4",
        "#D8F1EE": "#F4E1E5",
        "#EEF7F6": "#F8F1F3",
        "#164B47": "#51232D",
        "#B7E2DD": "#E6BDC5",
        "#82AAA6": "#C58B97",
        "#3F5553": "#614B50",
        "#294D4A": "#552F37",
        "#203A38": "#44272E",
        "#E2F3F1": "#F3E3E7",
    },
    "gray": {
        "#327F79": "#646E78",
        "#246B66": "#505861",
        "#2B756F": "#5A636D",
        "#4B9B94": "#7F8994",
        "#9ED8D2": "#C3C9D0",
        "#B7E4DF": "#D2D6DB",
        "#C9EEEA": "#E0E3E6",
        "#C5EBE7": "#D9DDE1",
        "#D8F1EE": "#E7E9EB",
        "#EEF7F6": "#F3F5F6",
        "#164B47": "#343A40",
        "#B7E2DD": "#D0D4D8",
        "#82AAA6": "#A5ADB5",
        "#3F5553": "#50565D",
        "#294D4A": "#363D44",
        "#203A38": "#292F35",
        "#E2F3F1": "#E6E8EA",
    },
}

PALETTE_RGB_REPLACEMENTS: dict[str, dict[tuple[int, int, int], tuple[int, int, int]]] = {
    "burgundy": {
        (50, 127, 121): (139, 58, 74),
        (37, 94, 89): (105, 43, 55),
        (158, 216, 210): (227, 173, 184),
        (58, 94, 90): (105, 72, 79),
        (63, 91, 88): (104, 75, 81),
        (35, 92, 87): (101, 42, 53),
        (42, 73, 70): (88, 58, 64),
        (29, 58, 55): (72, 41, 47),
        (216, 241, 238): (244, 225, 229),
        (46, 105, 99): (113, 49, 62),
        (245, 251, 250): (252, 247, 248),
        (239, 247, 246): (249, 241, 243),
        (232, 247, 245): (248, 235, 238),
        (43, 117, 111): (126, 52, 67),
        (244, 255, 253): (255, 246, 248),
        (220, 241, 238): (245, 227, 231),
        (242, 250, 249): (252, 246, 248),
        (226, 244, 242): (247, 232, 235),
        (246, 251, 250): (252, 247, 248),
        (40, 84, 80): (94, 53, 62),
        (52, 103, 98): (113, 61, 72),
        (45, 103, 97): (112, 52, 65),
        (39, 92, 87): (101, 46, 58),
        (48, 92, 88): (103, 56, 65),
        (44, 82, 79): (92, 51, 59),
        (27, 74, 70): (82, 40, 49),
        (47, 74, 72): (83, 57, 62),
        (55, 83, 80): (91, 62, 68),
    },
    "gray": {
        (50, 127, 121): (100, 110, 120),
        (37, 94, 89): (76, 84, 92),
        (158, 216, 210): (195, 201, 208),
        (58, 94, 90): (88, 95, 103),
        (63, 91, 88): (91, 97, 104),
        (35, 92, 87): (74, 82, 90),
        (42, 73, 70): (75, 81, 88),
        (29, 58, 55): (60, 66, 72),
        (216, 241, 238): (231, 233, 235),
        (46, 105, 99): (83, 91, 99),
        (245, 251, 250): (249, 250, 251),
        (239, 247, 246): (244, 246, 247),
        (232, 247, 245): (239, 241, 243),
        (43, 117, 111): (83, 92, 101),
        (244, 255, 253): (250, 251, 252),
        (220, 241, 238): (235, 237, 239),
        (242, 250, 249): (247, 248, 249),
        (226, 244, 242): (239, 241, 243),
        (246, 251, 250): (250, 251, 252),
        (40, 84, 80): (72, 78, 84),
        (52, 103, 98): (87, 94, 101),
        (45, 103, 97): (84, 91, 98),
        (39, 92, 87): (77, 84, 91),
        (48, 92, 88): (82, 88, 95),
        (44, 82, 79): (75, 81, 87),
        (27, 74, 70): (65, 71, 77),
        (47, 74, 72): (72, 77, 83),
        (55, 83, 80): (79, 84, 90),
    },
}

CUSTOM_DURATION_LIMITS: dict[str, tuple[int, int, int]] = {
    "eyes": (20, 120, 10),
    "general": (120, 600, 30),
    "neck": (60, 300, 30),
    "back": (60, 300, 30),
    "wrists": (30, 180, 30),
    "breathing": (60, 300, 30),
}


def _achievement_series(
    series: str,
    metric: str,
    targets: tuple[int, ...],
    icon: str,
    tone: str,
    title_en: str,
    title_ru: str,
    goal_en: str,
    goal_ru: str,
) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "id": f"{series}-{target}",
            "series": series,
            "level": level,
            "metric": metric,
            "target": target,
            "icon": icon,
            "tone": tone,
            "title_en": title_en,
            "title_ru": title_ru,
            "description_en": goal_en.format(target=target),
            "description_ru": goal_ru.format(target=target),
        }
        for level, target in enumerate(targets, 1)
    )


ACHIEVEMENTS: tuple[dict[str, Any], ...] = (
    *_achievement_series(
        "rhythm",
        "breaks",
        (1, 10, 25, 50, 100, 250, 500, 1000),
        "general",
        "sea",
        "Work rhythm",
        "Рабочий ритм",
        "Complete {target} guided breaks.",
        "Завершите паузы с подсказками: {target}.",
    ),
    *_achievement_series(
        "eyes",
        "eye_breaks",
        (1, 5, 15, 25, 50, 100, 250, 500),
        "eyes",
        "violet",
        "Eyes off screen",
        "Взгляд вдаль",
        "Complete {target} eye-rest sessions.",
        "Завершите паузы для глаз: {target}.",
    ),
    *_achievement_series(
        "movement",
        "movement_breaks",
        (1, 5, 15, 25, 50, 100, 250, 500),
        "general",
        "green",
        "Keep moving",
        "Больше движения",
        "Complete {target} movement, neck, back or hand sessions.",
        "Завершите разминки для тела, шеи, спины или рук: {target}.",
    ),
    *_achievement_series(
        "breathing",
        "breathing_sessions",
        (1, 3, 10, 30, 50, 75, 150, 300),
        "breathing",
        "sky",
        "Calm rhythm",
        "Спокойный ритм",
        "Finish {target} paced-breathing sessions.",
        "Завершите дыхательные сессии: {target}.",
    ),
    *_achievement_series(
        "habits",
        "habit_marks",
        (1, 7, 30, 60, 100, 250, 500, 1000),
        "water",
        "amber",
        "Healthy habits",
        "Полезные привычки",
        "Record {target} completed habit goals.",
        "Отметьте выполнение полезных привычек: {target}.",
    ),
    *_achievement_series(
        "variety",
        "break_kinds",
        (1, 2, 3, 4, 5, 6, 7, 8),
        "neck",
        "rose",
        "Balanced routine",
        "Разумный баланс",
        "Complete {target} different types of guided activity.",
        "Завершите разные виды активности: {target}.",
    ),
    *_achievement_series(
        "streak",
        "break_streak",
        (3, 7, 14, 30, 60, 100, 180, 365),
        "back",
        "deep",
        "Steady rhythm",
        "Стабильный ритм",
        "Take at least one guided break on {target} consecutive days.",
        "Делайте хотя бы одну паузу подряд столько дней: {target}.",
    ),
)

REMINDER_META = {
    "eyes": {
        "title": "Разгрузка для глаз",
        "eyebrow": "Короткая пауза для зрения",
        "icon": "eyes",
        "image": "eyes-guide.png",
        "steps": [
            "Отвернитесь от экрана и найдите объект не ближе 6 метров.",
            "Расслабьте взгляд; не пытайтесь сфокусироваться силой.",
            "Медленно и полностью моргните 8–10 раз.",
        ],
        "note": "Если упражнение вызывает неприятные ощущения, остановитесь. Повторяющиеся симптомы лучше обсудить с врачом.",
        "variants": [
            {
                "title": "Дайте глазам даль",
                "eyebrow": "20 секунд без ближнего фокуса",
                "duration_seconds": 20,
                "steps": [
                    "Отвернитесь от экрана и найдите объект не ближе 6 метров.",
                    "Расслабьте взгляд и медленно полностью моргните 8–10 раз.",
                ],
                "step_seconds": [14, 6],
            },
            {
                "title": "Мягкая смена фокуса",
                "eyebrow": "45 секунд для зрительной дистанции",
                "duration_seconds": 45,
                "steps": [
                    "Посмотрите вдаль, не пытаясь сфокусироваться силой.",
                    "Переведите взгляд на предмет на расстоянии вытянутой руки.",
                    "Снова спокойно смотрите вдаль.",
                    "Ещё раз переведите взгляд на предмет ближе.",
                    "Вернитесь к дальнему объекту и завершите медленными полными морганиями.",
                ],
                "step_seconds": [10, 5, 10, 5, 15],
            },
            {
                "title": "Спокойный отдых без экрана",
                "eyebrow": "Отдых для глаз без ближнего фокуса",
                "duration_seconds": 60,
                "steps": [
                    "Мягко закройте глаза, не зажмуриваясь и не надавливая руками.",
                    "Откройте глаза и спокойно смотрите вдаль.",
                    "Медленно полностью моргните 8 раз и ещё немного не возвращайтесь к экрану.",
                ],
                "step_seconds": [20, 20, 20],
            },
        ],
    },
    "general": {
        "title": "Активная пауза",
        "eyebrow": "Каждый раз немного по-разному",
        "icon": "general",
        "steps": [
            "Пройдитесь 2–3 минуты в спокойном темпе.",
            "Сведите лопатки 8 раз без подъёма плеч.",
            "Поднимитесь на носки 10 раз, держась за устойчивую опору.",
            "Сделайте 5 мягких разгибаний корпуса стоя — только в комфортной амплитуде.",
        ],
        "note": "Двигайтесь только комфортно. Повторяющиеся или усиливающиеся симптомы лучше обсудить с врачом.",
        "image": "general-guide.png",
        "variants": [
            {
                "title": "Шаги и смена позы",
                "eyebrow": "5 минут лёгкого движения",
                "duration_seconds": 300,
                "steps": [
                    "Пройдитесь 2–3 минуты в спокойном темпе.",
                    "Поднимитесь на носки 10 раз, держась за устойчивую опору.",
                    "Мягко сведите лопатки 8 раз, не поднимая плечи.",
                    "Спокойно постойте или продолжите ходьбу до конца паузы.",
                ],
            },
            {
                "title": "Разомните верх тела",
                "eyebrow": "3 минуты без резких движений",
                "duration_seconds": 180,
                "steps": [
                    "Опустите плечи и мягко сведите лопатки 8 раз.",
                    "Согните руки под прямым углом и медленно разведите их в стороны 6 раз.",
                    "Встряхните кисти и полностью раскройте пальцы 10 раз.",
                    "Завершите минутой спокойной ходьбы.",
                ],
            },
            {
                "title": "Ноги и устойчивость",
                "eyebrow": "3 минуты рядом с опорой",
                "duration_seconds": 180,
                "steps": [
                    "Встаньте и перенесите вес с одной ноги на другую 8 раз.",
                    "Сделайте 5 спокойных вставаний со стула, если это комфортно.",
                    "Поднимитесь на носки 10 раз, держась за устойчивую опору.",
                    "Пройдитесь до конца паузы.",
                ],
            },
            {
                "title": "Спокойная общая разминка",
                "eyebrow": "5 минут на всё тело",
                "duration_seconds": 300,
                "steps": [
                    "Пройдитесь около двух минут.",
                    "Сведите лопатки 8 раз без подъёма плеч.",
                    "Сделайте 5 мягких разгибаний корпуса стоя в комфортной амплитуде.",
                    "Поднимитесь на носки 10 раз и завершите спокойным дыханием.",
                ],
            },
            {
                "title": "Стопы и равновесие",
                "eyebrow": "Мягкая пауза рядом с опорой",
                "duration_seconds": 240,
                "steps": [
                    "Встаньте рядом с устойчивой опорой и перенесите вес с ноги на ногу 8 раз.",
                    "Поднимитесь на носки 8 раз, не торопясь.",
                    "Поочерёдно слегка приподнимите носки стоп 8 раз, сохраняя корпус ровным.",
                    "Пройдитесь в спокойном темпе до конца паузы.",
                ],
            },
            {
                "title": "Стул, лопатки и ходьба",
                "eyebrow": "Смена нагрузки на всё тело",
                "duration_seconds": 240,
                "steps": [
                    "Сделайте 5 медленных вставаний со стула, если это комфортно.",
                    "Опустите плечи и сведите лопатки 8 раз.",
                    "Полностью раскройте пальцы и расслабьте их 10 раз.",
                    "Завершите спокойной ходьбой.",
                ],
            },
            {
                "title": "Стена, руки и шаги",
                "eyebrow": "Спокойная силовая пауза",
                "duration_seconds": 240,
                "steps": [
                    "Пройдитесь около минуты в спокойном темпе.",
                    "Сделайте 5 медленных отжиманий от стены, если плечам комфортно.",
                    "Мягко сведите лопатки 8 раз, не поднимая плечи.",
                    "Завершите ходьбой и расслабьте руки.",
                ],
            },
            {
                "title": "Стул и голени",
                "eyebrow": "Ноги рядом с устойчивой опорой",
                "duration_seconds": 240,
                "steps": [
                    "Сделайте 5 медленных вставаний со стула, при необходимости помогая себе руками.",
                    "Поднимитесь на носки 8 раз рядом с устойчивой опорой.",
                    "Медленно перенесите вес с одной ноги на другую 8 раз.",
                    "Спокойно пройдитесь до конца паузы.",
                ],
            },
            {
                "title": "Шаги на месте и опора",
                "eyebrow": "Небольшая смена нагрузки",
                "duration_seconds": 180,
                "steps": [
                    "Шагайте на месте 30–45 секунд, держась за опору при необходимости.",
                    "Перенесите вес с одной стопы на другую 8 раз.",
                    "Поочерёдно слегка приподнимите носки 8 раз.",
                    "Завершите спокойной ходьбой.",
                ],
            },
            {
                "title": "Боковые шаги и лопатки",
                "eyebrow": "Движение в разных направлениях",
                "duration_seconds": 240,
                "steps": [
                    "Сделайте по 4 небольших шага в каждую сторону рядом с устойчивой опорой.",
                    "Мягко сведите лопатки 8 раз.",
                    "Полностью раскройте пальцы 10 раз и расслабьте кисти.",
                    "Пройдитесь в спокойном темпе.",
                ],
            },
            {
                "title": "Небольшой круг у стола",
                "eyebrow": "Пять минут на основные группы мышц",
                "duration_seconds": 300,
                "steps": [
                    "Пройдитесь около минуты.",
                    "Сделайте 5 вставаний со стула и 5 отжиманий от стены, если это комфортно.",
                    "Поднимитесь на носки 8 раз рядом с опорой.",
                    "Оставшееся время спокойно походите.",
                ],
            },
            {
                "title": "Спокойная смена уровней",
                "eyebrow": "Сидя, стоя и в движении",
                "duration_seconds": 240,
                "steps": [
                    "Дважды медленно сядьте и встаньте с устойчивого стула.",
                    "Стоя, согните и разогните руки 8 раз без веса.",
                    "Шагайте на месте 30 секунд рядом с опорой.",
                    "Завершите минутой спокойной ходьбы.",
                ],
            },
        ],
    },
    "neck": {
        "title": "Мягкая разминка шеи",
        "eyebrow": "3 минуты без рывков",
        "icon": "neck",
        "steps": [
            "Выпрямитесь и слегка уведите подбородок назад 6 раз.",
            "Поверните голову вправо и влево по 4 раза в безболезненной амплитуде.",
            "Наклоните ухо к плечу по 3 раза, не поднимая плечи.",
            "Опустите и сведите лопатки 8 раз; дышите свободно.",
        ],
        "note": "Не делайте круговых вращений и не давите рукой. При неприятных ощущениях остановитесь и посоветуйтесь с врачом.",
        "image": "neck-guide.png",
        "variants": [
            {
                "title": "Верните голову над плечами",
                "eyebrow": "3 минуты на осанку",
                "duration_seconds": 180,
                "steps": [
                    "Сядьте с опорой под спиной, опустите плечи и смотрите прямо.",
                    "Мягко уведите подбородок назад 5 раз, не наклоняя голову вниз.",
                    "Сведите лопатки назад и немного вниз 6 раз, без подъёма плеч.",
                    "Встаньте и спокойно пройдитесь до конца паузы.",
                ],
            },
            {
                "title": "Повороты без усилия",
                "eyebrow": "3 минуты комфортной подвижности",
                "duration_seconds": 180,
                "steps": [
                    "Сядьте ровно, расслабьте челюсть и держите подбородок слегка отведённым назад.",
                    "Медленно поверните голову вправо и влево по 3 раза — только до комфортной границы.",
                    "Наклоните ухо к плечу по 3 раза с каждой стороны, не поднимая плечи и не помогая рукой.",
                    "Вернитесь в нейтральное положение и сделайте 5 спокойных движений плечами вниз.",
                ],
            },
            {
                "title": "Отпустите плечевой пояс",
                "eyebrow": "3 минуты для плеч и лопаток",
                "duration_seconds": 180,
                "steps": [
                    "Опустите руки вдоль тела и дайте плечам расслабиться.",
                    "Поднимите плечи к ушам и мягко отпустите вниз 5 раз, без резкого сбрасывания.",
                    "Сведите лопатки назад и вниз 6 раз, каждый раз ненадолго расслабляясь.",
                    "Согните руки под прямым углом и медленно разведите их в стороны 6 раз.",
                ],
            },
            {
                "title": "Верх тела без напряжения",
                "eyebrow": "3 минуты смены движений",
                "duration_seconds": 180,
                "steps": [
                    "Мягко уведите подбородок назад 5 раз и оставьте шею длинной.",
                    "Поверните голову вправо и влево по 3 раза в комфортной амплитуде.",
                    "Полностью раскройте пальцы и легко встряхните кисти.",
                    "Опустите плечи, сведите лопатки 6 раз и завершите короткой ходьбой.",
                ],
            },
            {
                "title": "Лопатки и открытая грудная клетка",
                "eyebrow": "Спокойная разгрузка верхней части тела",
                "duration_seconds": 180,
                "steps": [
                    "Сядьте с опорой под спиной и дайте рукам свободно опуститься.",
                    "Мягко разведите ключицы и сведите лопатки назад и вниз 6 раз.",
                    "Уведите подбородок назад 5 раз, сохраняя взгляд прямо.",
                    "Расслабьте плечи и немного пройдитесь.",
                ],
            },
            {
                "title": "Микродвижения для шеи и плеч",
                "eyebrow": "Без долгих удержаний",
                "duration_seconds": 150,
                "steps": [
                    "Выпрямитесь без напряжения и сделайте 4 мягких движения подбородком назад.",
                    "Поверните голову вправо и влево по 2 раза в небольшой комфортной амплитуде.",
                    "Поднимите плечи к ушам и спокойно опустите 5 раз.",
                    "Сведите лопатки 5 раз и вернитесь в нейтральную позу.",
                ],
            },
        ],
    },
    "drops": {
        "title": "Капли для глаз",
        "eyebrow": "По вашей схеме врача",
        "icon": "drops",
        "image": "drops-guide.png",
        "steps": [
            "Проверьте название препарата и назначенное время.",
            "Вымойте руки и не касайтесь наконечником глаза или ресниц.",
            "После закапывания мягко закройте глаз; не трите его.",
        ],
        "note": "Интервал в приложении — только таймер. Режим использования любых средств лучше согласовать с врачом.",
    },
    "back": {
        "title": "Разгрузите поясницу",
        "eyebrow": "3 минуты мягкого движения",
        "icon": "back",
        "image": "back-guide.png",
        "steps": [
            "Встаньте и спокойно пройдитесь около минуты.",
            "Перенесите вес с одной ноги на другую 8 раз, держась за опору.",
            "Сделайте 5 мягких разгибаний корпуса стоя в комфортной амплитуде.",
        ],
        "note": "При неприятных или усиливающихся ощущениях остановитесь. Индивидуальный комплекс лучше согласовать с врачом.",
        "variants": [
            {
                "title": "Пройдитесь и смените опору",
                "eyebrow": "3 минуты мягкого движения",
                "duration_seconds": 180,
                "steps": [
                    "Встаньте и спокойно пройдитесь около минуты.",
                    "Держась за устойчивую опору, перенесите вес с одной ноги на другую 8 раз.",
                    "Сделайте 5 очень небольших разгибаний корпуса стоя — только если это комфортно.",
                    "Вернитесь к спокойной ходьбе до конца паузы.",
                ],
            },
            {
                "title": "Ноги помогают спине",
                "eyebrow": "3 минуты рядом со стулом",
                "duration_seconds": 180,
                "steps": [
                    "Поставьте стопы устойчиво и сделайте 5 медленных вставаний со стула, если это комфортно.",
                    "Поднимитесь на носки 8 раз, держась за устойчивую опору.",
                    "Перенесите вес с одной ноги на другую по 4 раза.",
                    "Пройдитесь в спокойном темпе до конца паузы.",
                ],
            },
            {
                "title": "Свободная смена позы",
                "eyebrow": "3 минуты без растяжки через силу",
                "duration_seconds": 180,
                "steps": [
                    "Встаньте, выпрямитесь без напряжения и сделайте несколько спокойных шагов.",
                    "Держась за спинку стула, слегка согните и выпрямите колени 6 раз.",
                    "Сделайте 6 небольших шагов в сторону и обратно, сохраняя корпус ровным.",
                    "Завершите минутой спокойной ходьбы.",
                ],
            },
            {
                "title": "Встаньте без спешки",
                "eyebrow": "Движение вместо долгого сидения",
                "duration_seconds": 180,
                "steps": [
                    "Сядьте ближе к краю устойчивого стула и поставьте стопы на пол.",
                    "Медленно встаньте и снова сядьте 5 раз, используя удобную опору при необходимости.",
                    "Стоя поднимитесь на носки 6 раз.",
                    "Пройдитесь до конца паузы.",
                ],
            },
            {
                "title": "Шаги в разные стороны",
                "eyebrow": "Мягкая активность для таза и ног",
                "duration_seconds": 180,
                "steps": [
                    "Пройдитесь около минуты в спокойном темпе.",
                    "Держась за опору, сделайте по 4 небольших шага в сторону и обратно.",
                    "Перенесите вес вперёд и назад по 4 раза без глубокого наклона.",
                    "Вернитесь к обычной ходьбе.",
                ],
            },
        ],
    },
    "wrists": {
        "title": "Отпустите кисти",
        "eyebrow": "90 секунд для рук",
        "icon": "wrists",
        "image": "wrists-guide.png",
        "steps": [
            "Опустите руки и мягко встряхните кистями.",
            "Сожмите и полностью раскройте пальцы 10 раз.",
            "Сделайте по 5 медленных кругов кистями в каждую сторону.",
        ],
        "note": "Не тяните пальцы другой рукой через дискомфорт. Повторяющиеся симптомы лучше обсудить с врачом.",
        "variants": [
            {
                "title": "Раскройте и отпустите кисти",
                "eyebrow": "90 секунд свободного движения",
                "duration_seconds": 90,
                "steps": [
                    "Опустите руки и легко встряхните расслабленными кистями.",
                    "Медленно раскройте пальцы и соберите их в мягкий, не напряжённый кулак 8 раз.",
                    "Сделайте по 4 небольших круга кистями в каждую сторону.",
                ],
            },
            {
                "title": "Пальцы меняют форму",
                "eyebrow": "90 секунд без силовой растяжки",
                "duration_seconds": 90,
                "steps": [
                    "Начните с прямых расслабленных пальцев и нейтральных запястий.",
                    "Согните пальцы только в крупных суставах, сохраняя их прямыми, затем раскройте ладонь 5 раз.",
                    "Соберите пальцы в мягкий кулак и снова полностью раскройте их 5 раз.",
                    "Завершите лёгким встряхиванием рук.",
                ],
            },
            {
                "title": "Запястья и предплечья",
                "eyebrow": "90 секунд активной подвижности",
                "duration_seconds": 90,
                "steps": [
                    "Согните локти и медленно поверните ладони вверх, затем вниз 6 раз.",
                    "Не помогая другой рукой, мягко направьте кисти вверх и вниз по 5 раз.",
                    "Разведите пальцы, расслабьте их и повторите 6 раз.",
                    "Опустите руки и легко встряхните кистями.",
                ],
            },
            {
                "title": "Большой палец встречает остальные",
                "eyebrow": "Точная подвижность пальцев",
                "duration_seconds": 90,
                "steps": [
                    "Держите запястья нейтрально и расслабьте ладони.",
                    "По очереди коснитесь большим пальцем каждого кончика пальца 3 раза.",
                    "Широко, но без усилия разведите пальцы и расслабьте их 6 раз.",
                    "Соберите мягкий кулак, раскройте ладони и легко встряхните кисти.",
                ],
            },
            {
                "title": "Перезагрузка после клавиатуры",
                "eyebrow": "Активные движения без давления рукой",
                "duration_seconds": 90,
                "steps": [
                    "Уберите руки от клавиатуры и положите предплечья на стол.",
                    "Мягко поднимите и опустите кисти по 5 раз, не помогая другой рукой.",
                    "Поверните ладони вверх и вниз 6 раз.",
                    "Раскройте пальцы, расслабьте и встряхните руки.",
                ],
            },
        ],
    },
    "breathing": {
        "title": "Две минуты тише",
        "eyebrow": "Спокойное дыхание",
        "icon": "breathing",
        "image": "breathing-guide.png",
        "steps": [
            "Поставьте стопы на пол и расслабьте плечи.",
            "Вдыхайте спокойно, затем делайте чуть более длинный выдох.",
            "Не задерживайте дыхание и не старайтесь дышать максимально глубоко.",
        ],
        "note": "Если кружится голова, вернитесь к обычному дыханию.",
        "variants": [
            {
                "title": "Тихое естественное дыхание",
                "eyebrow": "2 минуты без глубоких вдохов через силу",
                "duration_seconds": 120,
                "steps": [
                    "Сядьте с опорой под спиной, поставьте стопы на пол и расслабьте плечи.",
                    "Положите ладонь на нижние рёбра и просто замечайте их спокойное движение.",
                    "Дышите тихо и обычно; не увеличивайте вдох специально.",
                ],
            },
            {
                "title": "Ровный спокойный ритм",
                "eyebrow": "2 минуты мягкого счёта",
                "duration_seconds": 120,
                "steps": [
                    "Устройтесь удобно и сначала сделайте несколько обычных вдохов и выдохов.",
                    "Мягко вдыхайте примерно на 3 счёта и выдыхайте примерно на 3 счёта.",
                    "После нескольких циклов вернитесь к естественному дыханию.",
                ],
            },
            {
                "title": "Чуть более длинный выдох",
                "eyebrow": "2 минуты без задержки дыхания",
                "duration_seconds": 120,
                "steps": [
                    "Расслабьте плечи и сделайте несколько обычных дыхательных циклов.",
                    "Если комфортно, вдыхайте примерно на 2 счёта и спокойно выдыхайте на 4.",
                    "Не выталкивайте воздух; при дискомфорте сразу вернитесь к обычному ритму.",
                ],
            },
            {
                "title": "Пауза без счёта",
                "eyebrow": "Только наблюдение за естественным дыханием",
                "duration_seconds": 120,
                "steps": [
                    "Сядьте удобно, поставьте стопы на пол и расслабьте плечи.",
                    "Не меняя дыхание специально, замечайте спокойный вдох и выдох.",
                    "Если выдох сам становится чуть длиннее — позвольте ему, но ничего не форсируйте.",
                ],
            },
            {
                "title": "Движение нижних рёбер",
                "eyebrow": "Мягкое внимание к дыханию",
                "duration_seconds": 120,
                "steps": [
                    "Положите ладони по бокам нижних рёбер и оставьте плечи расслабленными.",
                    "Дышите обычно и замечайте небольшое движение рёбер под ладонями.",
                    "Уберите руки и завершите несколькими естественными дыхательными циклами.",
                ],
            },
        ],
    },
    "water": {
        "title": "Проверьте жажду",
        "eyebrow": "Без обязательной нормы",
        "icon": "water",
        "image": "water-guide.png",
        "steps": [
            "Если хочется пить — сделайте несколько глотков воды.",
            "Заодно отведите взгляд от экрана и смените позу.",
        ],
        "note": "Не нужно пить через силу; ограничения врача по жидкости всегда важнее напоминания.",
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(base))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def normalize_color_theme(value: Any) -> str:
    theme = str(value or "teal")
    return theme if theme in COLOR_PALETTES else "teal"


def _palette_rgb(rgb: tuple[int, int, int], color_theme: str) -> tuple[int, int, int]:
    """Move any remaining teal-tinted CSS colour into the selected palette."""
    red, green, blue = (channel / 255 for channel in rgb)
    hue, lightness, saturation = colorsys.rgb_to_hls(red, green, blue)
    if not (0.42 <= hue <= 0.56 and saturation >= 0.04):
        return rgb
    if color_theme == "burgundy":
        hue = 0.975
        saturation = min(0.58, saturation * 0.88 + 0.025)
    elif color_theme == "gray":
        hue = 0.583
        saturation = min(0.12, saturation * 0.22)
    else:
        return rgb
    converted = colorsys.hls_to_rgb(hue, lightness, saturation)
    return tuple(round(channel * 255) for channel in converted)


def render_palette_css(stylesheet: str, color_theme: str) -> str:
    """Render the base teal stylesheet in the selected accent palette."""
    palette = normalize_color_theme(color_theme)
    if palette == "teal":
        return stylesheet
    rendered = stylesheet
    for source, target in PALETTE_HEX_REPLACEMENTS[palette].items():
        rendered = re.sub(re.escape(source), target, rendered, flags=re.IGNORECASE)
    for source, target in PALETTE_RGB_REPLACEMENTS[palette].items():
        pattern = rf"rgba\(\s*{source[0]}\s*,\s*{source[1]}\s*,\s*{source[2]}\s*,"
        replacement = f"rgba({target[0]},{target[1]},{target[2]},"
        rendered = re.sub(pattern, replacement, rendered)

    def replace_hex(match: re.Match[str]) -> str:
        value = match.group(0)
        rgb = tuple(int(value[index : index + 2], 16) for index in (1, 3, 5))
        converted = _palette_rgb(rgb, palette)
        return "#" + "".join(f"{channel:02X}" for channel in converted)

    def replace_rgb(match: re.Match[str]) -> str:
        prefix, red, green, blue = match.groups()
        converted = _palette_rgb((int(red), int(green), int(blue)), palette)
        return f"{prefix}({converted[0]},{converted[1]},{converted[2]},"

    rendered = re.sub(r"#[0-9A-Fa-f]{6}\b", replace_hex, rendered)
    rendered = re.sub(
        r"\b(rgba)\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,",
        replace_rgb,
        rendered,
    )
    return rendered


def screen_is_being_used(idle_seconds: float, idle_threshold: float, fullscreen: bool) -> bool:
    """Count a visible fullscreen window even when the pointer stays still."""
    return bool(fullscreen) or idle_seconds < idle_threshold


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else json.loads(json.dumps(default))
    except (OSError, ValueError, TypeError):
        return json.loads(json.dumps(default))


def play_guidance_sound(config: dict[str, Any], cue: str = "step") -> None:
    if not bool(config.get("guided_sound_enabled", True)):
        return
    sound_files = {
        "start": Path("/usr/share/sounds/Yaru/stereo/message.oga"),
        "step": Path("/usr/share/sounds/Yaru/stereo/message-new-instant.oga"),
        "done": Path("/usr/share/sounds/Yaru/stereo/complete.oga"),
    }
    sound_file = sound_files.get(cue, sound_files["step"])
    volume = max(-30.0, min(0.0, float(config.get("guided_sound_volume", -8.0))))
    try:
        sound_argument = (
            ["--file", str(sound_file)] if sound_file.exists() else ["--id", "message-new-instant"]
        )
        subprocess.Popen(
            ["canberra-gtk-play", *sound_argument, "--volume", str(volume), "--description", "Здорово"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        display = Gdk.Display.get_default()
        if display:
            display.beep()


def guided_step_seconds(total_seconds: int, step_count: int, preferred: Any = None) -> list[int]:
    if isinstance(preferred, list) and len(preferred) == step_count:
        values = [max(1, int(value)) for value in preferred]
        if sum(values) == total_seconds:
            return values
    if step_count <= 0:
        return []
    base, remainder = divmod(max(step_count, total_seconds), step_count)
    return [base + (1 if index < remainder else 0) for index in range(step_count)]


def normalize_clock(value: Any, fallback: str) -> str:
    """Return a safe HH:MM value for persisted schedule settings."""
    try:
        hour, minute = (int(part) for part in str(value).split(":", 1))
    except (TypeError, ValueError):
        return fallback
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return fallback
    return f"{hour:02d}:{minute:02d}"


def automatic_theme_is_dark(
    current: datetime | None = None,
    light_time: str = "07:00",
    dark_time: str = "21:00",
) -> bool:
    """Resolve the scheduled theme, including schedules that cross midnight."""
    now = current or datetime.now()
    light_hour, light_minute = (int(part) for part in normalize_clock(light_time, "07:00").split(":"))
    dark_hour, dark_minute = (int(part) for part in normalize_clock(dark_time, "21:00").split(":"))
    current_minutes = now.hour * 60 + now.minute
    light_minutes = light_hour * 60 + light_minute
    dark_minutes = dark_hour * 60 + dark_minute
    if light_minutes == dark_minutes:
        return False
    if light_minutes < dark_minutes:
        return not light_minutes <= current_minutes < dark_minutes
    return dark_minutes <= current_minutes < light_minutes


class Config:
    def __init__(self) -> None:
        CONFIG_HOME.mkdir(parents=True, exist_ok=True)
        saved_data = load_json(CONFIG_FILE, {})
        self.data = deep_merge(DEFAULT_CONFIG, saved_data)
        if not bool(self.data.get("language_selected", False)) or self.data.get("language") not in (
            "en",
            "ru",
        ):
            self.data["language"] = "en"
        theme_mode = saved_data.get("theme_mode")
        if theme_mode not in ("light", "dark", "auto"):
            theme_mode = "dark" if bool(self.data.get("dark_mode", False)) else "light"
        self.data["theme_mode"] = theme_mode
        self.data["color_theme"] = normalize_color_theme(self.data.get("color_theme"))
        self.data["sidebar_collapsed"] = bool(self.data.get("sidebar_collapsed", False))
        self.data["theme_light_time"] = normalize_clock(self.data.get("theme_light_time"), "07:00")
        self.data["theme_dark_time"] = normalize_clock(self.data.get("theme_dark_time"), "21:00")
        self.data["snooze_minutes"] = max(1, min(20, int(self.data.get("snooze_minutes", 5))))
        if int(self.data.get("training_duration_days", 30)) not in COURSE_DURATIONS:
            self.data["training_duration_days"] = 30
        if self.data.get("training_fitness_level") not in FITNESS_LEVELS:
            self.data["training_fitness_level"] = "beginner"
        legacy_training_days = max(2, min(5, int(self.data.get("training_days_per_week", 3))))
        try:
            training_weekdays = normalize_weekdays(
                saved_data.get("training_weekdays"),
                legacy_training_days,
            )
        except ValueError:
            training_weekdays = normalize_weekdays(None, legacy_training_days)
        self.data["training_weekdays"] = list(training_weekdays)
        self.data["training_days_per_week"] = len(training_weekdays)
        self.data["training_reminders_enabled"] = bool(self.data.get("training_reminders_enabled", True))
        training_reminder_time = self.data.get("training_reminder_time")
        self.data["training_reminder_time"] = (
            normalize_clock(training_reminder_time, "18:00")
            if isinstance(training_reminder_time, str) and training_reminder_time.strip()
            else None
        )
        habits = self.data.get("habits")
        if not isinstance(habits, list):
            self.data["habits"] = json.loads(json.dumps(DEFAULT_CONFIG["habits"]))
        else:
            prepared_habits: list[dict[str, Any]] = []
            for index, habit in enumerate(habits[:20]):
                if not isinstance(habit, dict):
                    continue
                habit_id = str(habit.get("id") or f"habit-{index}")[:64]
                title = str(habit.get("title") or "Полезная привычка")[:80]
                reminder_time = str(habit.get("reminder_time") or "18:00")
                try:
                    hour, minute = (int(part) for part in reminder_time.split(":", 1))
                    reminder_time = f"{max(0, min(23, hour)):02d}:{max(0, min(59, minute)):02d}"
                except (TypeError, ValueError):
                    reminder_time = "18:00"
                prepared_habits.append(
                    {
                        "id": habit_id,
                        "title": title,
                        "enabled": bool(habit.get("enabled", True)),
                        "target": max(1, min(10, int(habit.get("target", 1)))),
                        "reminder_enabled": bool(habit.get("reminder_enabled", False)),
                        "reminder_time": reminder_time,
                        "icon": str(habit.get("icon") or "general")
                        if str(habit.get("icon") or "general") in REMINDER_META
                        else "general",
                    }
                )
            self.data["habits"] = prepared_habits
        self.data.pop("game_mode", None)
        # A dashboard pause is intentionally session-scoped and never survives a restart.
        self.data["manual_pause"] = False
        self.save()

    def save(self) -> None:
        atomic_json(CONFIG_FILE, self.data)

    def reminder(self, kind: str) -> dict[str, Any]:
        return self.data["reminders"][kind]


class UsageDatabase:
    def __init__(self, path: Path = DB_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS daily_app (
                day TEXT NOT NULL,
                app_id TEXT NOT NULL,
                app_name TEXT NOT NULL,
                seconds REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (day, app_id)
            );
            CREATE TABLE IF NOT EXISTS usage_segments (
                id INTEGER PRIMARY KEY,
                started_at REAL NOT NULL,
                ended_at REAL NOT NULL,
                app_id TEXT NOT NULL,
                app_name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reminder_events (
                id INTEGER PRIMARY KEY,
                created_at REAL NOT NULL,
                kind TEXT NOT NULL,
                action TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS wellness_checkins (
                id INTEGER PRIMARY KEY,
                created_at REAL NOT NULL,
                headache INTEGER NOT NULL,
                eyes INTEGER NOT NULL,
                neck INTEGER NOT NULL,
                back INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS habit_events (
                id INTEGER PRIMARY KEY,
                created_at REAL NOT NULL,
                habit_id TEXT NOT NULL,
                amount INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS app_notifications (
                id TEXT PRIMARY KEY,
                created_at REAL NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                page TEXT NOT NULL DEFAULT 'today',
                is_read INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS achievement_unlocks (
                id TEXT PRIMARY KEY,
                unlocked_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS training_enrollments (
                id INTEGER PRIMARY KEY,
                course_id TEXT NOT NULL,
                duration_days INTEGER NOT NULL,
                fitness_level TEXT NOT NULL DEFAULT 'beginner',
                days_per_week INTEGER NOT NULL DEFAULT 3,
                weekdays TEXT NOT NULL DEFAULT '[0,2,4]',
                started_at REAL NOT NULL,
                current_day INTEGER NOT NULL DEFAULT 1,
                completed_at REAL,
                is_active INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS training_events (
                id INTEGER PRIMARY KEY,
                enrollment_id INTEGER NOT NULL,
                created_at REAL NOT NULL,
                course_day INTEGER NOT NULL,
                session_key TEXT NOT NULL,
                duration_seconds REAL NOT NULL DEFAULT 0,
                UNIQUE(enrollment_id, course_day)
            );
            CREATE INDEX IF NOT EXISTS idx_segments_started ON usage_segments(started_at);
            CREATE INDEX IF NOT EXISTS idx_events_created ON reminder_events(created_at);
            CREATE INDEX IF NOT EXISTS idx_wellness_created ON wellness_checkins(created_at);
            CREATE INDEX IF NOT EXISTS idx_habit_events_created ON habit_events(created_at);
            CREATE INDEX IF NOT EXISTS idx_app_notifications_created ON app_notifications(created_at);
            CREATE INDEX IF NOT EXISTS idx_training_events_created ON training_events(created_at);
            """
        )
        event_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(reminder_events)")}
        if "duration_seconds" not in event_columns:
            self.conn.execute(
                "ALTER TABLE reminder_events ADD COLUMN duration_seconds REAL NOT NULL DEFAULT 0"
            )
        training_columns = {
            row["name"] for row in self.conn.execute("PRAGMA table_info(training_enrollments)")
        }
        if "fitness_level" not in training_columns:
            self.conn.execute(
                "ALTER TABLE training_enrollments ADD COLUMN fitness_level TEXT NOT NULL DEFAULT 'beginner'"
            )
        if "days_per_week" not in training_columns:
            self.conn.execute(
                "ALTER TABLE training_enrollments ADD COLUMN days_per_week INTEGER NOT NULL DEFAULT 3"
            )
        if "weekdays" not in training_columns:
            self.conn.execute(
                "ALTER TABLE training_enrollments ADD COLUMN weekdays TEXT NOT NULL DEFAULT '[0,2,4]'"
            )
            for count in (2, 3, 4, 5):
                encoded = json.dumps(list(normalize_weekdays(None, count)), separators=(",", ":"))
                self.conn.execute(
                    "UPDATE training_enrollments SET weekdays=? WHERE days_per_week=?",
                    (encoded, count),
                )
        for legacy_id, current_id in COURSE_ALIASES.items():
            self.conn.execute(
                "UPDATE training_enrollments SET course_id=? WHERE course_id=?",
                (current_id, legacy_id),
            )
        self.conn.commit()
        self._segment_id: int | None = None
        self._segment_app: str | None = None
        self._segment_last = 0.0

    def close(self) -> None:
        try:
            connection = getattr(self, "conn", None)
            if connection:
                connection.close()
        except sqlite3.ProgrammingError:
            pass

    def __del__(self) -> None:
        self.close()

    def record_tick(self, now: float, app_id: str, app_name: str, seconds: float) -> None:
        if seconds <= 0 or seconds > 15:
            return
        day = datetime.fromtimestamp(now).date().isoformat()
        app_id = app_id or "unknown"
        app_name = app_name or "Неизвестное приложение"
        self.conn.execute(
            """INSERT INTO daily_app(day, app_id, app_name, seconds) VALUES(?,?,?,?)
               ON CONFLICT(day, app_id) DO UPDATE SET
                 app_name=excluded.app_name, seconds=daily_app.seconds+excluded.seconds""",
            (day, app_id, app_name, seconds),
        )
        if self._segment_id and self._segment_app == app_id and now - self._segment_last <= 15:
            self.conn.execute("UPDATE usage_segments SET ended_at=? WHERE id=?", (now, self._segment_id))
        else:
            cursor = self.conn.execute(
                "INSERT INTO usage_segments(started_at, ended_at, app_id, app_name) VALUES(?,?,?,?)",
                (now - seconds, now, app_id, app_name),
            )
            self._segment_id = int(cursor.lastrowid)
            self._segment_app = app_id
        self._segment_last = now
        self.conn.commit()

    def log_reminder(
        self,
        kind: str,
        action: str,
        now: float | None = None,
        duration_seconds: float = 0.0,
    ) -> None:
        self.conn.execute(
            "INSERT INTO reminder_events(created_at, kind, action, duration_seconds) VALUES(?,?,?,?)",
            (now or time.time(), kind, action, max(0.0, float(duration_seconds))),
        )
        self.conn.commit()

    def total_for_day(self, day: str | None = None) -> float:
        day = day or datetime.now().date().isoformat()
        row = self.conn.execute(
            "SELECT COALESCE(SUM(seconds),0) total FROM daily_app WHERE day=?", (day,)
        ).fetchone()
        return float(row["total"])

    def top_apps(self, days: int = 1, limit: int = 8) -> list[sqlite3.Row]:
        since = (datetime.now().date() - timedelta(days=days - 1)).isoformat()
        return list(
            self.conn.execute(
                """SELECT app_id, MAX(app_name) app_name, SUM(seconds) seconds
                   FROM daily_app WHERE day>=? GROUP BY app_id ORDER BY seconds DESC LIMIT ?""",
                (since, limit),
            )
        )

    def daily_totals(self, days: int = 7) -> list[tuple[str, float]]:
        start = datetime.now().date() - timedelta(days=days - 1)
        rows = {
            row["day"]: float(row["seconds"])
            for row in self.conn.execute(
                "SELECT day, SUM(seconds) seconds FROM daily_app WHERE day>=? GROUP BY day",
                (start.isoformat(),),
            )
        }
        return [
            ((start + timedelta(days=i)).isoformat(), rows.get((start + timedelta(days=i)).isoformat(), 0.0))
            for i in range(days)
        ]

    def daily_app_totals(self, days: int = 7) -> list[sqlite3.Row]:
        start = datetime.now().date() - timedelta(days=days - 1)
        return list(
            self.conn.execute(
                """SELECT day, app_id, MAX(app_name) app_name, SUM(seconds) seconds
                   FROM daily_app WHERE day>=?
                   GROUP BY day, app_id ORDER BY day, seconds DESC""",
                (start.isoformat(),),
            )
        )

    def hourly_app_totals(self, day: str) -> list[dict[str, Any]]:
        date_value = datetime.fromisoformat(day).date()
        start = datetime.combine(date_value, datetime.min.time()).timestamp()
        end = start + 86400
        totals: dict[tuple[int, str, str], float] = {}
        rows = self.conn.execute(
            """SELECT started_at, ended_at, app_id, app_name
               FROM usage_segments
               WHERE ended_at>? AND started_at<? ORDER BY started_at""",
            (start, end),
        )
        for row in rows:
            segment_start = max(start, float(row["started_at"]))
            segment_end = min(end, float(row["ended_at"]))
            while segment_start < segment_end:
                hour = min(23, int((segment_start - start) // 3600))
                boundary = min(segment_end, start + (hour + 1) * 3600)
                key = (hour, str(row["app_id"]), str(row["app_name"]))
                totals[key] = totals.get(key, 0.0) + max(0.0, boundary - segment_start)
                segment_start = boundary
        return [
            {"hour": hour, "app_id": app_id, "app_name": app_name, "seconds": seconds}
            for (hour, app_id, app_name), seconds in sorted(totals.items())
        ]

    def earliest_usage_day(self) -> date:
        row = self.conn.execute(
            """SELECT MIN(day) day FROM (
                 SELECT MIN(day) day FROM daily_app
                 UNION ALL
                 SELECT MIN(date(created_at, 'unixepoch', 'localtime')) day FROM wellness_checkins
               )"""
        ).fetchone()
        if row and row["day"]:
            return datetime.fromisoformat(str(row["day"])).date()
        return datetime.now().date()

    def reminder_counts(self, days: int = 1) -> tuple[int, int]:
        since = time.time() - days * 86400
        done = self.conn.execute(
            "SELECT COUNT(*) n FROM reminder_events WHERE created_at>=? AND action='done'", (since,)
        ).fetchone()["n"]
        snoozed = self.conn.execute(
            "SELECT COUNT(*) n FROM reminder_events WHERE created_at>=? AND action='snooze'", (since,)
        ).fetchone()["n"]
        return int(done), int(snoozed)

    def exercise_overview(self, days: int = 7) -> sqlite3.Row:
        since = time.time() - days * 86400
        return self.conn.execute(
            """SELECT
                 SUM(CASE WHEN action='done' THEN 1 ELSE 0 END) done,
                 SUM(CASE WHEN action='snooze' THEN 1 ELSE 0 END) snoozed,
                 COALESCE(SUM(CASE WHEN action='done' THEN duration_seconds ELSE 0 END), 0) seconds
               FROM reminder_events WHERE created_at>=?""",
            (since,),
        ).fetchone()

    def exercise_overview_for_day(self, day: str) -> sqlite3.Row:
        return self.conn.execute(
            """SELECT
                 SUM(CASE WHEN action='done' THEN 1 ELSE 0 END) done,
                 SUM(CASE WHEN action='snooze' THEN 1 ELSE 0 END) snoozed,
                 COALESCE(SUM(CASE WHEN action='done' THEN duration_seconds ELSE 0 END), 0) seconds
               FROM reminder_events
               WHERE date(created_at, 'unixepoch', 'localtime')=?""",
            (day,),
        ).fetchone()

    def exercise_by_kind(self, days: int = 7) -> list[sqlite3.Row]:
        since = time.time() - days * 86400
        return list(
            self.conn.execute(
                """SELECT kind,
                 SUM(CASE WHEN action='done' THEN 1 ELSE 0 END) done,
                 SUM(CASE WHEN action='snooze' THEN 1 ELSE 0 END) snoozed,
                 COALESCE(SUM(CASE WHEN action='done' THEN duration_seconds ELSE 0 END), 0) seconds
               FROM reminder_events WHERE created_at>=? AND action IN ('done','snooze')
               GROUP BY kind ORDER BY done DESC, seconds DESC""",
                (since,),
            )
        )

    def save_wellness(self, headache: int, eyes: int, neck: int, back: int, now: float | None = None) -> None:
        values = tuple(max(0, min(10, int(value))) for value in (headache, eyes, neck, back))
        self.conn.execute(
            "INSERT INTO wellness_checkins(created_at, headache, eyes, neck, back) VALUES(?,?,?,?,?)",
            (now or time.time(), *values),
        )
        self.conn.commit()

    def latest_wellness(self) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM wellness_checkins ORDER BY created_at DESC LIMIT 1"
        ).fetchone()

    def latest_wellness_for_day(self, day: str) -> sqlite3.Row | None:
        return self.conn.execute(
            """SELECT * FROM wellness_checkins
               WHERE date(created_at, 'unixepoch', 'localtime')=?
               ORDER BY created_at DESC LIMIT 1""",
            (day,),
        ).fetchone()

    def wellness_comparison(self, day: str) -> tuple[sqlite3.Row | None, sqlite3.Row | None]:
        columns = "AVG(headache) headache, AVG(eyes) eyes, AVG(neck) neck, AVG(back) back"
        current = self.conn.execute(
            f"""SELECT date(created_at, 'unixepoch', 'localtime') day, {columns}
                FROM wellness_checkins
                WHERE date(created_at, 'unixepoch', 'localtime')=? GROUP BY day""",
            (day,),
        ).fetchone()
        previous = self.conn.execute(
            f"""SELECT date(created_at, 'unixepoch', 'localtime') day, {columns}
                FROM wellness_checkins
                WHERE date(created_at, 'unixepoch', 'localtime')<?
                GROUP BY day ORDER BY day DESC LIMIT 1""",
            (day,),
        ).fetchone()
        return current, previous

    def wellness_period_summary(self, days: int = 30) -> sqlite3.Row:
        start_day = datetime.now().date() - timedelta(days=max(1, days) - 1)
        return self.conn.execute(
            """SELECT AVG(headache) headache, AVG(eyes) eyes,
                      AVG(neck) neck, AVG(back) back,
                      COUNT(DISTINCT date(created_at, 'unixepoch', 'localtime')) recorded_days,
                      MIN(date(created_at, 'unixepoch', 'localtime')) first_day,
                      MAX(date(created_at, 'unixepoch', 'localtime')) last_day
               FROM wellness_checkins
               WHERE date(created_at, 'unixepoch', 'localtime')>=?""",
            (start_day.isoformat(),),
        ).fetchone()

    def wellness_summary_between(self, start_day: str, end_day: str) -> sqlite3.Row:
        return self.conn.execute(
            """SELECT AVG(headache) headache, AVG(eyes) eyes,
                      AVG(neck) neck, AVG(back) back,
                      COUNT(DISTINCT date(created_at, 'unixepoch', 'localtime')) recorded_days,
                      MIN(date(created_at, 'unixepoch', 'localtime')) first_day,
                      MAX(date(created_at, 'unixepoch', 'localtime')) last_day
               FROM wellness_checkins
               WHERE date(created_at, 'unixepoch', 'localtime') BETWEEN ? AND ?""",
            (start_day, end_day),
        ).fetchone()

    def total_between(self, start_day: str, end_day: str) -> float:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(seconds),0) total FROM daily_app WHERE day BETWEEN ? AND ?",
            (start_day, end_day),
        ).fetchone()
        return float(row["total"])

    def exercise_overview_between(self, start_day: str, end_day: str) -> sqlite3.Row:
        return self.conn.execute(
            """SELECT
                 SUM(CASE WHEN action='done' THEN 1 ELSE 0 END) done,
                 SUM(CASE WHEN action='snooze' THEN 1 ELSE 0 END) snoozed,
                 COALESCE(SUM(CASE WHEN action='done' THEN duration_seconds ELSE 0 END), 0) seconds
               FROM reminder_events
               WHERE date(created_at, 'unixepoch', 'localtime') BETWEEN ? AND ?""",
            (start_day, end_day),
        ).fetchone()

    def wellness_range_comparison(
        self, start_day: date, end_day: date
    ) -> tuple[sqlite3.Row | None, sqlite3.Row | None]:
        span = (end_day - start_day).days + 1
        previous_end = start_day - timedelta(days=1)
        previous_start = previous_end - timedelta(days=span - 1)
        columns = "AVG(headache) headache, AVG(eyes) eyes, AVG(neck) neck, AVG(back) back"
        current = self.conn.execute(
            f"""SELECT {columns} FROM wellness_checkins
                WHERE date(created_at, 'unixepoch', 'localtime') BETWEEN ? AND ?
                HAVING COUNT(*) > 0""",
            (start_day.isoformat(), end_day.isoformat()),
        ).fetchone()
        previous = self.conn.execute(
            f"""SELECT {columns} FROM wellness_checkins
                WHERE date(created_at, 'unixepoch', 'localtime') BETWEEN ? AND ?
                HAVING COUNT(*) > 0""",
            (previous_start.isoformat(), previous_end.isoformat()),
        ).fetchone()
        return current, previous

    def total_for_period(self, days: int = 30) -> float:
        start_day = datetime.now().date() - timedelta(days=max(1, days) - 1)
        row = self.conn.execute(
            "SELECT COALESCE(SUM(seconds),0) total FROM daily_app WHERE day>=?",
            (start_day.isoformat(),),
        ).fetchone()
        return float(row["total"])

    def has_wellness_today(self) -> bool:
        start = datetime.combine(datetime.now().date(), datetime.min.time()).timestamp()
        return bool(
            self.conn.execute(
                "SELECT 1 FROM wellness_checkins WHERE created_at>=? LIMIT 1", (start,)
            ).fetchone()
        )

    def wellness_days(self, days: int = 7) -> list[dict[str, Any]]:
        start = datetime.now().date() - timedelta(days=days - 1)
        checkins = {
            str(row["day"]): row
            for row in self.conn.execute(
                """SELECT date(created_at, 'unixepoch', 'localtime') day,
                          AVG(headache) headache, AVG(eyes) eyes,
                          AVG(neck) neck, AVG(back) back, COUNT(*) checkins
                   FROM wellness_checkins
                   WHERE created_at>=?
                   GROUP BY day""",
                (datetime.combine(start, datetime.min.time()).timestamp(),),
            )
        }
        screen = dict(self.daily_totals(days))
        events = {
            str(row["day"]): int(row["done"])
            for row in self.conn.execute(
                """SELECT date(created_at, 'unixepoch', 'localtime') day, COUNT(*) done
                   FROM reminder_events
                   WHERE created_at>=? AND action='done'
                   GROUP BY day""",
                (datetime.combine(start, datetime.min.time()).timestamp(),),
            )
        }
        result: list[dict[str, Any]] = []
        for offset in range(days):
            day = (start + timedelta(days=offset)).isoformat()
            row = checkins.get(day)
            result.append(
                {
                    "day": day,
                    "headache": float(row["headache"]) if row else None,
                    "eyes": float(row["eyes"]) if row else None,
                    "neck": float(row["neck"]) if row else None,
                    "back": float(row["back"]) if row else None,
                    "checkins": int(row["checkins"]) if row else 0,
                    "screen_seconds": float(screen.get(day, 0.0)),
                    "breaks": int(events.get(day, 0)),
                }
            )
        return result

    def log_habit(self, habit_id: str, amount: int = 1, now: float | None = None) -> None:
        if not habit_id or amount == 0:
            return
        self.conn.execute(
            "INSERT INTO habit_events(created_at, habit_id, amount) VALUES(?,?,?)",
            (now or time.time(), habit_id, max(-1, min(1, int(amount)))),
        )
        self.conn.commit()

    def habit_count(self, habit_id: str, day: str | None = None) -> int:
        day = day or datetime.now().date().isoformat()
        row = self.conn.execute(
            """SELECT COALESCE(SUM(amount),0) amount FROM habit_events
               WHERE habit_id=? AND date(created_at, 'unixepoch', 'localtime')=?""",
            (habit_id, day),
        ).fetchone()
        return max(0, int(row["amount"] or 0))

    def habit_week_count(self, habit_id: str, days: int = 7) -> int:
        start = datetime.now().date() - timedelta(days=max(1, days) - 1)
        row = self.conn.execute(
            """SELECT COALESCE(SUM(amount),0) amount FROM habit_events
               WHERE habit_id=? AND date(created_at, 'unixepoch', 'localtime')>=?""",
            (habit_id, start.isoformat()),
        ).fetchone()
        return max(0, int(row["amount"] or 0))

    def habit_streak(self, habit_id: str, target: int = 1) -> int:
        target = max(1, int(target))
        cursor = datetime.now().date()
        if self.habit_count(habit_id, cursor.isoformat()) < target:
            cursor -= timedelta(days=1)
        streak = 0
        while streak < 365 and self.habit_count(habit_id, cursor.isoformat()) >= target:
            streak += 1
            cursor -= timedelta(days=1)
        return streak

    def breathing_overview(self, days: int = 7) -> sqlite3.Row:
        start = datetime.now().date() - timedelta(days=max(1, days) - 1)
        return self.conn.execute(
            """SELECT COUNT(*) sessions, COALESCE(SUM(duration_seconds),0) seconds
               FROM reminder_events
               WHERE kind='breathing' AND action='done'
                 AND date(created_at, 'unixepoch', 'localtime')>=?""",
            (start.isoformat(),),
        ).fetchone()

    def active_training(self) -> sqlite3.Row | None:
        return self.conn.execute(
            """SELECT * FROM training_enrollments
               WHERE is_active=1 ORDER BY started_at DESC, id DESC LIMIT 1"""
        ).fetchone()

    def training_available_today(self, enrollment_id: int, now: float | None = None) -> bool:
        row = self.conn.execute(
            """SELECT MAX(created_at) created_at FROM training_events
               WHERE enrollment_id=?""",
            (int(enrollment_id),),
        ).fetchone()
        if not row or row["created_at"] is None:
            return True
        completed = datetime.fromtimestamp(float(row["created_at"])).date()
        return completed < datetime.fromtimestamp(now or time.time()).date()

    def start_training(
        self,
        course_id: str,
        duration_days: int,
        fitness_level: str = "beginner",
        days_per_week: int = 3,
        now: float | None = None,
        weekdays: Any = None,
    ) -> sqlite3.Row:
        course_id = normalize_course_id(course_id)
        if course_id not in COURSES:
            raise ValueError(f"unknown course: {course_id}")
        if int(duration_days) not in COURSE_DURATIONS:
            raise ValueError(f"unsupported duration: {duration_days}")
        if fitness_level not in FITNESS_LEVELS:
            raise ValueError(f"unsupported fitness level: {fitness_level}")
        selected_weekdays = normalize_weekdays(weekdays, days_per_week)
        encoded_weekdays = json.dumps(list(selected_weekdays), separators=(",", ":"))
        with self.conn:
            self.conn.execute("UPDATE training_enrollments SET is_active=0 WHERE is_active=1")
            cursor = self.conn.execute(
                """INSERT INTO training_enrollments
                   (course_id, duration_days, fitness_level, days_per_week, weekdays,
                    started_at, current_day, is_active)
                   VALUES(?,?,?,?,?,?,1,1)""",
                (
                    course_id,
                    int(duration_days),
                    fitness_level,
                    len(selected_weekdays),
                    encoded_weekdays,
                    now or time.time(),
                ),
            )
        return self.conn.execute(
            "SELECT * FROM training_enrollments WHERE id=?", (int(cursor.lastrowid),)
        ).fetchone()

    def resumable_training(
        self,
        course_id: str,
        duration_days: int | None = None,
        fitness_level: str | None = None,
        days_per_week: int | None = None,
        weekdays: Any = None,
    ) -> sqlite3.Row | None:
        course_id = normalize_course_id(course_id)
        clauses = ["course_id=?", "is_active=0", "completed_at IS NULL"]
        values: list[Any] = [course_id]
        for column, value in (
            ("duration_days", duration_days),
            ("fitness_level", fitness_level),
            ("days_per_week", days_per_week),
        ):
            if value is not None:
                clauses.append(f"{column}=?")
                values.append(value)
        if weekdays is not None:
            selected = normalize_weekdays(weekdays, days_per_week or 3)
            clauses.append("weekdays=?")
            values.append(json.dumps(list(selected), separators=(",", ":")))
        return self.conn.execute(
            f"""SELECT * FROM training_enrollments WHERE {" AND ".join(clauses)}
                ORDER BY started_at DESC, id DESC LIMIT 1""",
            tuple(values),
        ).fetchone()

    def resume_training(self, enrollment_id: int) -> sqlite3.Row:
        enrollment = self.conn.execute(
            "SELECT * FROM training_enrollments WHERE id=?", (int(enrollment_id),)
        ).fetchone()
        if not enrollment or enrollment["completed_at"] is not None:
            raise ValueError("training course cannot be resumed")
        with self.conn:
            self.conn.execute("UPDATE training_enrollments SET is_active=0 WHERE is_active=1")
            self.conn.execute("UPDATE training_enrollments SET is_active=1 WHERE id=?", (int(enrollment_id),))
        return self.conn.execute(
            "SELECT * FROM training_enrollments WHERE id=?", (int(enrollment_id),)
        ).fetchone()

    def update_training_weekdays(
        self,
        enrollment_id: int,
        weekdays: Any,
    ) -> sqlite3.Row:
        return self.update_training_plan(enrollment_id, weekdays=weekdays)

    def update_training_plan(
        self,
        enrollment_id: int,
        *,
        weekdays: Any = None,
        fitness_level: str | None = None,
    ) -> sqlite3.Row:
        enrollment = self.conn.execute(
            "SELECT * FROM training_enrollments WHERE id=?", (int(enrollment_id),)
        ).fetchone()
        if not enrollment or not int(enrollment["is_active"]):
            raise ValueError("training course is not active")
        if weekdays is None:
            try:
                weekdays = json.loads(str(enrollment["weekdays"]))
            except (TypeError, ValueError):
                weekdays = None
        selected_weekdays = normalize_weekdays(weekdays, int(enrollment["days_per_week"]))
        level = fitness_level or str(enrollment["fitness_level"])
        if level not in FITNESS_LEVELS:
            raise ValueError("unsupported fitness level")
        encoded_weekdays = json.dumps(list(selected_weekdays), separators=(",", ":"))
        with self.conn:
            self.conn.execute(
                """UPDATE training_enrollments
                   SET fitness_level=?, days_per_week=?, weekdays=? WHERE id=?""",
                (level, len(selected_weekdays), encoded_weekdays, int(enrollment_id)),
            )
        return self.conn.execute(
            "SELECT * FROM training_enrollments WHERE id=?", (int(enrollment_id),)
        ).fetchone()

    def reset_training(
        self,
        enrollment_id: int,
        *,
        fitness_level: str | None = None,
        days_per_week: int | None = None,
        weekdays: Any = None,
        duration_days: int | None = None,
        now: float | None = None,
    ) -> sqlite3.Row:
        enrollment = self.conn.execute(
            "SELECT * FROM training_enrollments WHERE id=?", (int(enrollment_id),)
        ).fetchone()
        if not enrollment:
            raise ValueError("training course does not exist")
        level = fitness_level or str(enrollment["fitness_level"])
        saved_weekdays = weekdays
        if saved_weekdays is None:
            try:
                saved_weekdays = json.loads(str(enrollment["weekdays"]))
            except (TypeError, ValueError):
                saved_weekdays = None
        selected_weekdays = normalize_weekdays(
            saved_weekdays,
            int(days_per_week or enrollment["days_per_week"]),
        )
        weekly_days = len(selected_weekdays)
        encoded_weekdays = json.dumps(list(selected_weekdays), separators=(",", ":"))
        duration = int(duration_days or enrollment["duration_days"])
        if level not in FITNESS_LEVELS or weekly_days not in (2, 3, 4, 5) or duration not in COURSE_DURATIONS:
            raise ValueError("invalid training plan")
        with self.conn:
            self.conn.execute("UPDATE training_enrollments SET is_active=0 WHERE is_active=1")
            self.conn.execute("DELETE FROM training_events WHERE enrollment_id=?", (int(enrollment_id),))
            self.conn.execute(
                """UPDATE training_enrollments
                   SET duration_days=?, fitness_level=?, days_per_week=?, weekdays=?, started_at=?, current_day=1,
                       completed_at=NULL, is_active=1 WHERE id=?""",
                (
                    duration,
                    level,
                    weekly_days,
                    encoded_weekdays,
                    now or time.time(),
                    int(enrollment_id),
                ),
            )
        return self.conn.execute(
            "SELECT * FROM training_enrollments WHERE id=?", (int(enrollment_id),)
        ).fetchone()

    def complete_training_day(
        self,
        enrollment_id: int,
        course_day: int,
        session_key: str,
        duration_seconds: float = 0.0,
        now: float | None = None,
    ) -> bool:
        enrollment = self.conn.execute(
            "SELECT * FROM training_enrollments WHERE id=?", (int(enrollment_id),)
        ).fetchone()
        if not enrollment or not int(enrollment["is_active"]):
            raise ValueError("training course is not active")
        expected_day = int(enrollment["current_day"])
        if int(course_day) != expected_day:
            raise ValueError("training day does not match active progress")
        if not self.training_available_today(enrollment_id, now):
            raise ValueError("training day has already been completed today")
        completed_at = now or time.time()
        final_day = expected_day >= int(enrollment["duration_days"])
        with self.conn:
            self.conn.execute(
                """INSERT INTO training_events
                   (enrollment_id, created_at, course_day, session_key, duration_seconds)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(enrollment_id, course_day) DO UPDATE SET
                     created_at=excluded.created_at,
                     session_key=excluded.session_key,
                     duration_seconds=excluded.duration_seconds""",
                (
                    int(enrollment_id),
                    completed_at,
                    expected_day,
                    str(session_key)[:32],
                    max(0.0, float(duration_seconds)),
                ),
            )
            self.conn.execute(
                """UPDATE training_enrollments SET current_day=?, completed_at=?, is_active=?
                   WHERE id=?""",
                (
                    expected_day if final_day else expected_day + 1,
                    completed_at if final_day else None,
                    0 if final_day else 1,
                    int(enrollment_id),
                ),
            )
        return final_day

    def stop_training(self, enrollment_id: int) -> None:
        self.conn.execute("UPDATE training_enrollments SET is_active=0 WHERE id=?", (int(enrollment_id),))
        self.conn.commit()

    def training_summary(self, enrollment_id: int | None = None) -> sqlite3.Row:
        if enrollment_id is None:
            return self.conn.execute(
                """SELECT COUNT(*) completed_days,
                          COALESCE(SUM(duration_seconds),0) duration_seconds
                   FROM training_events"""
            ).fetchone()
        return self.conn.execute(
            """SELECT COUNT(*) completed_days,
                      COALESCE(SUM(duration_seconds),0) duration_seconds
               FROM training_events WHERE enrollment_id=?""",
            (int(enrollment_id),),
        ).fetchone()

    def training_history(self, limit: int = 8) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                """SELECT e.*,
                          COUNT(t.id) completed_days,
                          COALESCE(SUM(t.duration_seconds),0) duration_seconds
                   FROM training_enrollments e
                   LEFT JOIN training_events t ON t.enrollment_id=e.id
                   GROUP BY e.id ORDER BY e.started_at DESC LIMIT ?""",
                (max(1, int(limit)),),
            )
        )

    def training_calendar(self, start_day: date, end_day: date) -> list[sqlite3.Row]:
        start = datetime.combine(start_day, datetime.min.time()).timestamp()
        end = datetime.combine(end_day + timedelta(days=1), datetime.min.time()).timestamp()
        return list(
            self.conn.execute(
                """SELECT t.created_at, t.course_day, t.session_key, t.duration_seconds,
                          e.id enrollment_id, e.course_id, e.duration_days,
                          e.fitness_level, e.days_per_week, e.completed_at
                   FROM training_events t
                   JOIN training_enrollments e ON e.id=t.enrollment_id
                   WHERE t.created_at>=? AND t.created_at<?
                   ORDER BY t.created_at, t.id""",
                (start, end),
            )
        )

    def achievement_metrics(self) -> dict[str, int]:
        reminder = self.conn.execute(
            """SELECT
                   SUM(CASE WHEN action='done' THEN 1 ELSE 0 END) breaks,
                   SUM(CASE WHEN action='done' AND kind='eyes' THEN 1 ELSE 0 END) eye_breaks,
                   SUM(CASE WHEN action='done' AND kind IN ('general','neck','back','wrists')
                            THEN 1 ELSE 0 END) movement_breaks,
                   SUM(CASE WHEN action='done' AND kind='breathing' THEN 1 ELSE 0 END)
                       breathing_sessions,
                   COUNT(DISTINCT CASE WHEN action='done' THEN kind END) break_kinds
               FROM reminder_events"""
        ).fetchone()
        habit_marks = self.conn.execute(
            "SELECT COALESCE(SUM(amount), 0) amount FROM habit_events"
        ).fetchone()["amount"]
        days = [
            datetime.fromisoformat(str(row["day"])).date()
            for row in self.conn.execute(
                """SELECT DISTINCT date(created_at, 'unixepoch', 'localtime') day
                   FROM reminder_events WHERE action='done' ORDER BY day"""
            )
            if row["day"]
        ]
        longest_streak = 0
        current_streak = 0
        previous: date | None = None
        for day_value in days:
            current_streak = (
                current_streak + 1 if previous and day_value == previous + timedelta(days=1) else 1
            )
            longest_streak = max(longest_streak, current_streak)
            previous = day_value
        return {
            "breaks": int(reminder["breaks"] or 0),
            "eye_breaks": int(reminder["eye_breaks"] or 0),
            "movement_breaks": int(reminder["movement_breaks"] or 0),
            "breathing_sessions": int(reminder["breathing_sessions"] or 0),
            "habit_marks": max(0, int(habit_marks or 0)),
            "break_kinds": int(reminder["break_kinds"] or 0),
            "break_streak": longest_streak,
        }

    def achievement_progress(self) -> list[dict[str, Any]]:
        metrics = self.achievement_metrics()
        unlocked = {
            str(row["id"]): float(row["unlocked_at"])
            for row in self.conn.execute("SELECT id, unlocked_at FROM achievement_unlocks")
        }
        return [
            {
                **achievement,
                "progress": max(0, int(metrics.get(str(achievement["metric"]), 0))),
                "unlocked_at": unlocked.get(str(achievement["id"])),
            }
            for achievement in ACHIEVEMENTS
        ]

    def evaluate_achievements(self, now: float | None = None) -> list[dict[str, Any]]:
        unlocked_at = now or time.time()
        newly_unlocked: list[dict[str, Any]] = []
        with self.conn:
            for achievement in self.achievement_progress():
                if achievement["unlocked_at"] is not None:
                    continue
                if int(achievement["progress"]) < int(achievement["target"]):
                    continue
                cursor = self.conn.execute(
                    "INSERT OR IGNORE INTO achievement_unlocks(id, unlocked_at) VALUES(?,?)",
                    (str(achievement["id"]), unlocked_at),
                )
                if cursor.rowcount:
                    newly_unlocked.append({**achievement, "unlocked_at": unlocked_at})
        return newly_unlocked

    def add_notification(
        self,
        kind: str,
        title: str,
        body: str,
        page: str = "today",
        notification_id: str | None = None,
        now: float | None = None,
    ) -> str:
        created_at = now or time.time()
        notification_id = notification_id or f"{int(created_at * 1000)}-{kind}"
        self.conn.execute(
            """INSERT OR REPLACE INTO app_notifications
               (id, created_at, kind, title, body, page, is_read) VALUES(?,?,?,?,?,?,0)""",
            (notification_id, created_at, kind, title[:120], body[:300], page),
        )
        self.conn.execute(
            "DELETE FROM app_notifications WHERE id NOT IN (SELECT id FROM app_notifications ORDER BY created_at DESC LIMIT 80)"
        )
        self.conn.commit()
        return notification_id

    def notifications(self, limit: int = 20) -> list[sqlite3.Row]:
        return list(
            self.conn.execute(
                "SELECT * FROM app_notifications ORDER BY created_at DESC LIMIT ?", (max(1, limit),)
            )
        )

    def unread_notifications(self) -> int:
        return int(
            self.conn.execute("SELECT COUNT(*) amount FROM app_notifications WHERE is_read=0").fetchone()[
                "amount"
            ]
        )

    def mark_notifications_read(self) -> None:
        self.conn.execute("UPDATE app_notifications SET is_read=1 WHERE is_read=0")
        self.conn.commit()

    def backup_tables(self) -> dict[str, list[dict[str, Any]]]:
        tables = {
            "daily_app": ("day", "app_id", "app_name", "seconds"),
            "usage_segments": ("id", "started_at", "ended_at", "app_id", "app_name"),
            "reminder_events": ("id", "created_at", "kind", "action", "duration_seconds"),
            "wellness_checkins": ("id", "created_at", "headache", "eyes", "neck", "back"),
            "habit_events": ("id", "created_at", "habit_id", "amount"),
            "app_notifications": ("id", "created_at", "kind", "title", "body", "page", "is_read"),
            "achievement_unlocks": ("id", "unlocked_at"),
            "training_enrollments": (
                "id",
                "course_id",
                "duration_days",
                "fitness_level",
                "days_per_week",
                "weekdays",
                "started_at",
                "current_day",
                "completed_at",
                "is_active",
            ),
            "training_events": (
                "id",
                "enrollment_id",
                "created_at",
                "course_day",
                "session_key",
                "duration_seconds",
            ),
        }
        return {
            table: [
                dict(row) for row in self.conn.execute(f"SELECT {', '.join(columns)} FROM {table} ORDER BY 1")
            ]
            for table, columns in tables.items()
        }

    def restore_tables(self, payload: dict[str, Any]) -> None:
        tables = {
            "daily_app": ("day", "app_id", "app_name", "seconds"),
            "usage_segments": ("id", "started_at", "ended_at", "app_id", "app_name"),
            "reminder_events": ("id", "created_at", "kind", "action", "duration_seconds"),
            "wellness_checkins": ("id", "created_at", "headache", "eyes", "neck", "back"),
            "habit_events": ("id", "created_at", "habit_id", "amount"),
            "app_notifications": ("id", "created_at", "kind", "title", "body", "page", "is_read"),
            "achievement_unlocks": ("id", "unlocked_at"),
            "training_enrollments": (
                "id",
                "course_id",
                "duration_days",
                "fitness_level",
                "days_per_week",
                "weekdays",
                "started_at",
                "current_day",
                "completed_at",
                "is_active",
            ),
            "training_events": (
                "id",
                "enrollment_id",
                "created_at",
                "course_day",
                "session_key",
                "duration_seconds",
            ),
        }
        optional_tables = {
            "habit_events",
            "app_notifications",
            "achievement_unlocks",
            "training_enrollments",
            "training_events",
        }
        prepared: dict[str, list[tuple[Any, ...]]] = {}
        for table, columns in tables.items():
            rows = payload.get(table, [] if table in optional_tables else None)
            if not isinstance(rows, list):
                raise ValueError(f"missing table: {table}")
            prepared[table] = []
            for row in rows:
                if table == "training_enrollments" and isinstance(row, dict):
                    row = {
                        **row,
                        "course_id": normalize_course_id(str(row.get("course_id", ""))),
                        "fitness_level": row.get("fitness_level", "beginner"),
                        "days_per_week": row.get("days_per_week", 3),
                        "weekdays": row.get(
                            "weekdays",
                            json.dumps(
                                list(normalize_weekdays(None, int(row.get("days_per_week", 3)))),
                                separators=(",", ":"),
                            ),
                        ),
                    }
                if not isinstance(row, dict) or any(column not in row for column in columns):
                    raise ValueError(f"invalid row in {table}")
                prepared[table].append(tuple(row[column] for column in columns))
        with self.conn:
            for table, columns in tables.items():
                self.conn.execute(f"DELETE FROM {table}")
                if prepared[table]:
                    placeholders = ",".join("?" for _ in columns)
                    self.conn.executemany(
                        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
                        prepared[table],
                    )
        self._segment_id = None
        self._segment_app = None
        self._segment_last = 0.0


@dataclass
class Activity:
    active: bool
    app_id: str = "unknown"
    app_name: str = "Неизвестное приложение"
    fullscreen: bool = False
    screen_sharing: bool = False


class Scheduler:
    def __init__(
        self,
        config: Config,
        db: UsageDatabase,
        show_reminder: Callable[[dict[str, Any]], None],
        changed: Callable[[], None] | None = None,
        background_tracking: bool = False,
        prompt_wellness: Callable[[], None] | None = None,
        prompt_habit: Callable[[dict[str, Any]], None] | None = None,
        prompt_training: Callable[[sqlite3.Row, dict[str, Any], int], None] | None = None,
    ) -> None:
        self.config = config
        self.db = db
        self.show_reminder = show_reminder
        self.changed = changed or (lambda: None)
        self.prompt_wellness = prompt_wellness or (lambda: None)
        self.prompt_habit = prompt_habit or (lambda _habit: None)
        self.prompt_training = prompt_training or (lambda _enrollment, _plan, _count: None)
        self.state = deep_merge(
            {
                "accrued": {kind: 0.0 for kind in REMINDER_META},
                "snooze_until": {},
                "quiet_until": 0.0,
                "active_id": None,
                "rotation": {kind: 0 for kind in REMINDER_META},
                "last_completed_kind": None,
                "drops_day": datetime.now().date().isoformat(),
                "drops_done": 0,
                "wellness_prompt_day": datetime.now().date().isoformat(),
                "wellness_active_seconds": 0.0,
                "wellness_prompt_count": 0,
                "wellness_answered_day": None,
                "habit_reminder_day": datetime.now().date().isoformat(),
                "habit_reminders_sent": [],
                "training_reminder_day": datetime.now().date().isoformat(),
                "training_reminder_started_at": time.time(),
                "training_reminder_last_at": 0.0,
                "training_reminder_count": 0,
            },
            load_json(STATE_FILE, {}),
        )
        # Never restore an overlay after a crash/logout.
        self.state["active_id"] = None
        # A process start begins a fresh active-work interval. Persisted analytics,
        # rotations and daily counts remain intact, but an already-due timer must
        # never throw an exercise over the desktop as soon as the app launches.
        # Manual previews still bypass this through trigger().
        self.state["accrued"] = {kind: 0.0 for kind in REMINDER_META}
        self.state["session_started_at"] = time.time()
        self._active_kind: str | None = None
        self._last_tick = time.monotonic()
        self._last_response_id: str | None = None
        self._paused_players: list[str] = []
        self._last_save = 0.0
        self._idle_proxy: Gio.DBusProxy | None = None
        self.activity_source = "session"
        self._last_accessible_activity: Activity | None = None
        self._background_tracking = background_tracking
        self._activity_lock = threading.Lock()
        self._cached_activity = Activity(False)
        self._tracker_stop = threading.Event()
        self._tracker_thread: threading.Thread | None = None
        if background_tracking:
            self._tracker_thread = threading.Thread(
                target=self._activity_worker,
                name="zdorovo-activity",
                daemon=True,
            )
            self._tracker_thread.start()

    def stop(self) -> None:
        self._tracker_stop.set()
        if self._tracker_thread and self._tracker_thread.is_alive():
            self._tracker_thread.join(timeout=2)

    def _activity_worker(self) -> None:
        while not self._tracker_stop.is_set():
            started = time.monotonic()
            try:
                activity = self._read_activity_now()
            except Exception:
                activity = Activity(False)
            with self._activity_lock:
                self._cached_activity = activity
            elapsed = time.monotonic() - started
            # AT-SPI window discovery is the expensive fallback used until the
            # GNOME extension is live. Four seconds keeps app attribution useful
            # without stealing responsiveness from the desktop.
            self._tracker_stop.wait(max(0.5, 4.0 - elapsed))

    def extension_live(self) -> bool:
        heartbeat = load_json(DATA_HOME / "extension-heartbeat.json", {})
        return time.time() - float(heartbeat.get("timestamp", 0)) < 8

    def _fallback_idle_ms(self) -> float:
        try:
            if self._idle_proxy is None:
                self._idle_proxy = Gio.DBusProxy.new_for_bus_sync(
                    Gio.BusType.SESSION,
                    Gio.DBusProxyFlags.NONE,
                    None,
                    "org.gnome.Mutter.IdleMonitor",
                    "/org/gnome/Mutter/IdleMonitor/Core",
                    "org.gnome.Mutter.IdleMonitor",
                    None,
                )
            result = self._idle_proxy.call_sync("GetIdletime", None, Gio.DBusCallFlags.NONE, 1000, None)
            return float(result.unpack()[0])
        except GLib.Error:
            self._idle_proxy = None
            return 999999.0

    def read_activity(self) -> Activity:
        if self._background_tracking:
            with self._activity_lock:
                cached = self._cached_activity
                return Activity(
                    cached.active,
                    cached.app_id,
                    cached.app_name,
                    cached.fullscreen,
                    cached.screen_sharing,
                )
        return self._read_activity_now()

    def _read_activity_now(self) -> Activity:
        data = load_json(ACTIVITY_FILE, {})
        fresh = time.time() - float(data.get("timestamp", 0)) < 12
        screen_sharing = (
            bool(data.get("screen_sharing"))
            if fresh and "screen_sharing" in data
            else self._screen_sharing_atspi()
        )
        if not fresh:
            idle = self._fallback_idle_ms() / 1000
            atspi_activity = self._atspi_activity()
            if atspi_activity:
                self.activity_source = "atspi"
                self._last_accessible_activity = atspi_activity
                atspi_activity.active = idle < float(self.config.data["idle_threshold_seconds"])
                atspi_activity.screen_sharing = screen_sharing
                return atspi_activity
            if self._last_accessible_activity:
                self.activity_source = "atspi-cache"
                return Activity(
                    active=idle < float(self.config.data["idle_threshold_seconds"]),
                    app_id=self._last_accessible_activity.app_id,
                    app_name=self._last_accessible_activity.app_name,
                    fullscreen=False,
                    screen_sharing=screen_sharing,
                )
            self.activity_source = "session"
            return Activity(
                active=idle < float(self.config.data["idle_threshold_seconds"]),
                app_id="other-applications",
                app_name="Другие приложения",
                fullscreen=False,
                screen_sharing=screen_sharing,
            )
        self.activity_source = "gnome"
        idle = float(data.get("idle_ms", 999999)) / 1000
        fullscreen = bool(data.get("fullscreen", False))
        active = fresh and screen_is_being_used(
            idle,
            float(self.config.data["idle_threshold_seconds"]),
            fullscreen,
        )
        return Activity(
            active=active,
            app_id=str(data.get("app_id") or data.get("wm_class") or "unknown"),
            app_name=str(data.get("app_name") or data.get("wm_class") or "Неизвестное приложение"),
            fullscreen=fullscreen,
            screen_sharing=screen_sharing,
        )

    def _screen_sharing_atspi(self) -> bool:
        """Mirror GNOME's visible screen-sharing indicator in the current session."""
        try:
            desktop = Atspi.get_desktop(0)
            shell = next(
                (
                    desktop.get_child_at_index(index)
                    for index in range(desktop.get_child_count())
                    if (desktop.get_child_at_index(index).get_name() or "") == "gnome-shell"
                ),
                None,
            )
            if not shell:
                return False
            pending = [shell]
            visited = 0
            while pending and visited < 300:
                node = pending.pop()
                visited += 1
                name = (node.get_name() or "").casefold()
                states = node.get_state_set()
                is_share_control = "screen sharing" in name or "демонстрац" in name or "показ экрана" in name
                if (
                    is_share_control
                    and states.contains(Atspi.StateType.SHOWING)
                    and states.contains(Atspi.StateType.VISIBLE)
                ):
                    return True
                for index in range(min(node.get_child_count(), 40)):
                    pending.append(node.get_child_at_index(index))
        except Exception:
            return False
        return False

    def _atspi_activity(self) -> Activity | None:
        """Return the focused accessible app without ever persisting window titles."""
        try:
            desktop = Atspi.get_desktop(0)
            candidates: list[tuple[Any, Any]] = []
            for app_index in range(desktop.get_child_count()):
                app = desktop.get_child_at_index(app_index)
                app_name = (app.get_name() or "").strip().lower()
                if app_name == "gnome-shell":
                    continue
                child_count = app.get_child_count()
                for child_index in range(max(0, min(child_count, 16))):
                    window = app.get_child_at_index(child_index)
                    states = window.get_state_set()
                    if states.contains(Atspi.StateType.ACTIVE) or states.contains(Atspi.StateType.FOCUSED):
                        candidates.append((app, window))
            if not candidates:
                return None
            app, _window = candidates[-1]
            app_id, app_name = self._resolve_accessible_app(app)
            return Activity(True, app_id, app_name, False)
        except Exception:
            return None

    def _resolve_accessible_app(self, app: Any) -> tuple[str, str]:
        raw_name = (app.get_name() or "").strip()
        try:
            pid = int(app.get_process_id())
        except (TypeError, ValueError, GLib.Error):
            pid = 0
        process = ""
        if pid:
            with suppress(OSError):
                process = (
                    Path(f"/proc/{pid}/cmdline")
                    .read_bytes()
                    .replace(b"\0", b" ")
                    .decode("utf-8", "ignore")
                    .lower()
                )
        haystack = f"{raw_name} {process}".lower()
        known = (
            (("google chrome", "google-chrome"), "google-chrome.desktop", "Google Chrome"),
            (("telegram",), "telegram-desktop_telegram-desktop.desktop", "Telegram"),
            (
                ("visual studio code", "/snap/bin/code", " code ", "code "),
                "code_code.desktop",
                "Visual Studio Code",
            ),
            (("yandexmusic", "яндекс музыка"), "yandexmusic.desktop", "Яндекс Музыка"),
            (("zdorovo", "здорово", "healthbreak.py"), f"{APP_ID}.desktop", APP_NAME),
            (("firefox",), "firefox.desktop", "Firefox"),
        )
        for needles, app_id, display_name in known:
            if any(needle in haystack for needle in needles):
                return app_id, display_name
        safe_name = raw_name or (Path(process.split()[0]).name if process else "Приложение")
        safe_id = GLib.uri_escape_string(safe_name.lower().replace(" ", "-"), None, True) or "accessible-app"
        return f"atspi:{safe_id}", safe_name

    def tick(self) -> bool:
        now_mono = time.monotonic()
        delta = min(max(now_mono - self._last_tick, 0), 10)
        self._last_tick = now_mono
        now = time.time()
        today = datetime.now().date().isoformat()
        if self.state.get("drops_day") != today:
            self.state["drops_day"] = today
            self.state["drops_done"] = 0
            self.state["accrued"]["drops"] = 0.0
            self.state["snooze_until"].pop("drops", None)
        if self.state.get("wellness_prompt_day") != today:
            self.state["wellness_prompt_day"] = today
            self.state["wellness_active_seconds"] = 0.0
            self.state["wellness_prompt_count"] = 0
        if self.state.get("habit_reminder_day") != today:
            self.state["habit_reminder_day"] = today
            self.state["habit_reminders_sent"] = []
        if self.state.get("training_reminder_day") != today:
            self.state["training_reminder_day"] = today
            self.state["training_reminder_started_at"] = now
            self.state["training_reminder_last_at"] = 0.0
            self.state["training_reminder_count"] = 0
        activity = self.read_activity()
        if (
            activity.screen_sharing
            and bool(self.config.data.get("pause_on_screen_share", True))
            and self._active_kind
        ):
            deferred_kind = self._active_kind
            self.db.log_reminder(deferred_kind, "screen-share")
            self.state["snooze_until"][deferred_kind] = now + 60
            self._active_kind = None
            self.state["active_id"] = None
            self.resume_paused_media()
            self._save_state()
        break_open = bool(self._active_kind)
        reminders_paused = (
            break_open
            or bool(self.config.data["manual_pause"])
            or (bool(self.config.data.get("pause_on_fullscreen")) and activity.fullscreen)
            or (bool(self.config.data.get("pause_on_screen_share", True)) and activity.screen_sharing)
        )
        if activity.active and not break_open:
            self.db.record_tick(now, activity.app_id, activity.app_name, delta)
            self.state["wellness_active_seconds"] = (
                float(self.state.get("wellness_active_seconds", 0.0)) + delta
            )
        if activity.active and not reminders_paused:
            for kind, options in self.config.data["reminders"].items():
                if options.get("enabled", True):
                    self.state["accrued"][kind] = float(self.state["accrued"].get(kind, 0)) + delta

        self._consume_response()
        if (
            activity.active
            and not reminders_paused
            and not activity.fullscreen
            and not activity.screen_sharing
        ):
            self._maybe_prompt_wellness()
            self._maybe_prompt_habits()
        if not reminders_paused and not activity.fullscreen and not activity.screen_sharing:
            self._maybe_prompt_training(now)
        if not reminders_paused and not self._active_kind:
            self._maybe_show(now)
        if now - self._last_save > 10:
            self._save_state()
            self._last_save = now
        self.changed()
        return GLib.SOURCE_CONTINUE

    def _maybe_prompt_wellness(self) -> None:
        if not bool(self.config.data.get("wellness_checkin_enabled", True)) or not bool(
            self.config.data.get("wellness_reminders_enabled", True)
        ):
            return
        today = datetime.now().date().isoformat()
        if self._active_kind or self.state.get("wellness_answered_day") == today:
            return
        prompt_count = int(self.state.get("wellness_prompt_count", 0))
        thresholds = (30 * 60, 3 * 3600, 6 * 3600)
        if prompt_count >= len(thresholds):
            return
        if float(self.state.get("wellness_active_seconds", 0.0)) < thresholds[prompt_count]:
            return
        if self.db.has_wellness_today():
            self.mark_wellness_answered()
            return
        self.state["wellness_prompt_count"] = prompt_count + 1
        self.prompt_wellness()
        self._save_state()

    def mark_wellness_answered(self) -> None:
        self.state["wellness_answered_day"] = datetime.now().date().isoformat()
        self._save_state()

    def _maybe_prompt_habits(self) -> None:
        now = datetime.now()
        now_minutes = now.hour * 60 + now.minute
        sent = set(str(item) for item in self.state.get("habit_reminders_sent", []))
        changed = False
        for habit in self.config.data.get("habits", []):
            if not isinstance(habit, dict) or not habit.get("enabled") or not habit.get("reminder_enabled"):
                continue
            habit_id = str(habit.get("id") or "")
            if not habit_id or habit_id in sent:
                continue
            try:
                hour, minute = (int(part) for part in str(habit.get("reminder_time", "18:00")).split(":", 1))
            except (TypeError, ValueError):
                continue
            scheduled = hour * 60 + minute
            if now_minutes < scheduled or now_minutes - scheduled > 9:
                continue
            target = max(1, int(habit.get("target", 1)))
            if self.db.habit_count(habit_id) >= target:
                sent.add(habit_id)
                changed = True
                continue
            self.prompt_habit(habit)
            sent.add(habit_id)
            changed = True
        if changed:
            self.state["habit_reminders_sent"] = sorted(sent)
            self._save_state()

    def reset_training_reminders(self, now: float | None = None) -> None:
        current = time.time() if now is None else float(now)
        self.state["training_reminder_day"] = datetime.fromtimestamp(current).date().isoformat()
        self.state["training_reminder_started_at"] = current
        self.state["training_reminder_last_at"] = 0.0
        self.state["training_reminder_count"] = 0
        self._save_state()

    def _maybe_prompt_training(self, now: float | None = None) -> None:
        if not bool(self.config.data.get("training_reminders_enabled", True)):
            return
        current = time.time() if now is None else float(now)
        enrollment = self.db.active_training()
        if not enrollment:
            return
        enrollment_id = int(enrollment["id"])
        if not self.db.training_available_today(enrollment_id, current):
            return
        try:
            weekdays = normalize_weekdays(
                json.loads(str(enrollment["weekdays"])),
                int(enrollment["days_per_week"]),
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            weekdays = normalize_weekdays(None, int(enrollment["days_per_week"]))
        current_date = datetime.fromtimestamp(current)
        if current_date.weekday() not in weekdays:
            return
        start_weekday = datetime.fromtimestamp(float(enrollment["started_at"])).weekday()
        plan = training_day(
            str(enrollment["course_id"]),
            int(enrollment["current_day"]),
            int(enrollment["duration_days"]),
            str(self.config.data.get("language", "en")),
            str(enrollment["fitness_level"]),
            len(weekdays),
            weekdays,
            start_weekday,
        )
        if plan["kind"] == "rest" or not plan["exercises"]:
            return
        reminder_time = self.config.data.get("training_reminder_time")
        last_at = float(self.state.get("training_reminder_last_at", 0.0))
        count = int(self.state.get("training_reminder_count", 0))
        if isinstance(reminder_time, str) and reminder_time:
            hour, minute = (int(part) for part in normalize_clock(reminder_time, "18:00").split(":"))
            first_due = current_date.replace(hour=hour, minute=minute, second=0, microsecond=0).timestamp()
            due_at = first_due if count == 0 else last_at + 3600
        else:
            started_at = float(self.state.get("training_reminder_started_at", current))
            due_at = started_at + 2.5 * 3600 if count == 0 else last_at + 2.5 * 3600
        if current < due_at:
            return
        count += 1
        self.prompt_training(enrollment, plan, count)
        self.state["training_reminder_last_at"] = current
        self.state["training_reminder_count"] = count
        self._save_state()

    def _repeat_hold_seconds(self, kind: str, now: float | None = None) -> float:
        """Briefly hold a repeated activity when another one is almost due."""
        if self.state.get("last_completed_kind") != kind:
            return 0.0
        current_time = time.time() if now is None else now
        alternatives: list[float] = []
        for other, options in self.config.data["reminders"].items():
            if other == kind or not options.get("enabled"):
                continue
            if other == "drops" and int(self.state.get("drops_done", 0)) >= int(
                options.get("times_per_day", 4)
            ):
                continue
            remaining = max(
                self._target_seconds(other) - float(self.state["accrued"].get(other, 0)),
                float(self.state["snooze_until"].get(other, 0)) - current_time,
                0.0,
            )
            if remaining == 0:
                return 0.0
            if remaining <= 10 * 60:
                alternatives.append(remaining)
        return min(alternatives, default=0.0)

    def _maybe_show(self, now: float, preferred_kind: str | None = None) -> None:
        if now < float(self.state.get("quiet_until", 0)):
            return
        priority = ("general", "neck", "back", "eyes", "wrists", "breathing", "water", "drops")
        due: list[str] = []
        for kind in priority:
            options = self.config.reminder(kind)
            target = self._target_seconds(kind)
            if kind == "drops" and int(self.state.get("drops_done", 0)) >= int(
                options.get("times_per_day", 4)
            ):
                continue
            if (
                options.get("enabled")
                and float(self.state["accrued"].get(kind, 0)) >= target
                and now >= float(self.state["snooze_until"].get(kind, 0))
            ):
                due.append(kind)
        if not due:
            return
        # A longer active break already takes the user away from the screen, so
        # it can satisfy an eye-rest reminder without mixing eye instructions
        # into a movement routine.
        if preferred_kind in due:
            primary = str(preferred_kind)
        else:
            last_completed = self.state.get("last_completed_kind")
            different = [kind for kind in due if kind != last_completed]
            primary = different[0] if different else due[0]
            if len(due) == 1 and self._repeat_hold_seconds(primary, now) > 0:
                return
        combined = [primary]
        if primary in ("general", "neck"):
            for kind in due:
                if kind == "eyes":
                    combined.append(kind)
        reminder_id = f"{int(now * 1000)}-{primary}"
        meta = self._reminder_content(primary)
        steps = list(meta["steps"])
        if primary in CUSTOM_DURATION_LIMITS:
            duration_seconds = int(self.config.reminder(primary)["duration_seconds"])
        else:
            duration_seconds = int(
                meta.get("duration_seconds", self.config.reminder(primary)["duration_seconds"])
            )
        step_seconds = guided_step_seconds(duration_seconds, len(steps), meta.get("step_seconds"))
        language = str(self.config.data.get("language", "en"))
        eyebrow = (
            (
                f"Custom duration · {format_precise_duration(duration_seconds, language)}"
                if language == "en"
                else f"Настроенная длительность · {format_precise_duration(duration_seconds, language)}"
            )
            if primary in CUSTOM_DURATION_LIMITS
            else meta["eyebrow"]
        )
        payload = {
            "id": reminder_id,
            "kind": primary,
            "combined": combined,
            "title": meta["title"],
            "eyebrow": eyebrow,
            "icon": meta["icon"],
            "steps": steps,
            "note": meta["note"],
            "image": meta.get("image"),
            "duration_seconds": duration_seconds,
            "step_seconds": step_seconds,
            "variant_index": int(meta.get("variant_index", 0)),
            "created_at": now,
        }
        self._active_kind = primary
        self.state["active_id"] = reminder_id
        atomic_json(REMINDER_FILE, payload)
        self.db.log_reminder(primary, "shown", now)
        paused_players = pause_media_players()
        self._paused_players = list(paused_players) if isinstance(paused_players, list) else []
        self.show_reminder(payload)
        self._save_state()

    def _consume_response(self) -> None:
        response = load_json(RESPONSE_FILE, {})
        response_id = response.get("id")
        if not response_id or response_id == self._last_response_id:
            return
        self._last_response_id = str(response_id)
        if response_id != self.state.get("active_id"):
            return
        action = response.get("action")
        kind = self._active_kind
        if not kind or action not in ("done", "snooze"):
            return
        self.db.log_reminder(kind, action, duration_seconds=float(response.get("duration_seconds", 0.0)))
        if action == "done":
            payload = load_json(REMINDER_FILE, {})
            for completed in payload.get("combined", [kind]):
                self.state["accrued"][completed] = 0.0
                self.state["snooze_until"].pop(completed, None)
                if REMINDER_META[completed].get("variants"):
                    self.state["rotation"][completed] = int(self.state["rotation"].get(completed, 0)) + 1
                if completed == "drops":
                    self.state["drops_done"] = int(self.state.get("drops_done", 0)) + 1
            self.state["last_completed_kind"] = kind
        else:
            snooze_seconds = max(1, min(20, int(self.config.data.get("snooze_minutes", 5)))) * 60
            quiet_until = time.time() + snooze_seconds
            self.state["quiet_until"] = quiet_until
            self.state["snooze_until"][kind] = quiet_until
        self.resume_paused_media()
        self._active_kind = None
        self.state["active_id"] = None
        self._save_state()

    def resume_paused_media(self) -> None:
        if not self._paused_players:
            return
        players = self._paused_players
        self._paused_players = []
        resume_media_players(players)

    def next_due(self, kind: str) -> float | None:
        options = self.config.reminder(kind)
        if not options.get("enabled"):
            return None
        if kind == "drops" and int(self.state.get("drops_done", 0)) >= int(options.get("times_per_day", 4)):
            return None
        now = time.time()
        return max(
            self._target_seconds(kind) - float(self.state["accrued"].get(kind, 0)),
            float(self.state.get("snooze_until", {}).get(kind, 0)) - now,
            float(self.state.get("quiet_until", 0)) - now,
            self._repeat_hold_seconds(kind, now),
            0,
        )

    def next_title(self, kind: str) -> str:
        return str(self._reminder_content(kind)["title"])

    def trigger(self, kind: str) -> None:
        self.state["quiet_until"] = 0.0
        self.state["accrued"][kind] = self._target_seconds(kind)
        self.state["snooze_until"].pop(kind, None)
        if not self._active_kind:
            self._maybe_show(time.time(), preferred_kind=kind)

    def _save_state(self) -> None:
        atomic_json(STATE_FILE, self.state)

    def _target_seconds(self, kind: str) -> float:
        options = self.config.reminder(kind)
        if kind == "drops":
            # Spread reminders over a typical eight-hour active-computer day and cap them daily.
            return 8 * 3600 / max(1, int(options.get("times_per_day", 4)))
        return float(options["interval_minutes"]) * 60

    def _reminder_content(self, kind: str) -> dict[str, Any]:
        base = localized_reminder_meta(str(self.config.data.get("language", "en")), kind, REMINDER_META[kind])
        content = {key: value for key, value in base.items() if key != "variants"}
        variants = base.get("variants", [])
        if variants:
            index = int(self.state["rotation"].get(kind, 0)) % len(variants)
            content.update(variants[index])
            content["variant_index"] = index
        return content


def _mpris_playback_status(bus: Gio.DBusConnection, name: str) -> str:
    reply = bus.call_sync(
        name,
        "/org/mpris/MediaPlayer2",
        "org.freedesktop.DBus.Properties",
        "Get",
        GLib.Variant("(ss)", ("org.mpris.MediaPlayer2.Player", "PlaybackStatus")),
        GLib.VariantType.new("(v)"),
        Gio.DBusCallFlags.NONE,
        1000,
        None,
    )
    value = reply.unpack()[0]
    return str(value.unpack() if isinstance(value, GLib.Variant) else value)


def pause_media_players() -> list[str]:
    """Pause only players that are currently playing and return their bus names."""
    paused: list[str] = []
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = bus.call_sync(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "ListNames",
            None,
            GLib.VariantType.new("(as)"),
            Gio.DBusCallFlags.NONE,
            1000,
            None,
        )
        for name in reply.unpack()[0]:
            if not name.startswith("org.mpris.MediaPlayer2."):
                continue
            try:
                if _mpris_playback_status(bus, name) != "Playing":
                    continue
            except GLib.Error:
                continue
            bus.call_sync(
                name,
                "/org/mpris/MediaPlayer2",
                "org.mpris.MediaPlayer2.Player",
                "Pause",
                None,
                None,
                Gio.DBusCallFlags.NONE,
                1000,
                None,
            )
            paused.append(name)
    except GLib.Error:
        pass
    return paused


def resume_media_players(players: list[str]) -> int:
    """Resume only players previously paused by this app and still paused now."""
    resumed = 0
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        for name in players:
            try:
                # The list already contains only players that were Playing when
                # Zdorovo paused them. Play is idempotent and avoids a race where
                # Chromium has not yet published its Paused property.
                bus.call_sync(
                    name,
                    "/org/mpris/MediaPlayer2",
                    "org.mpris.MediaPlayer2.Player",
                    "Play",
                    None,
                    None,
                    Gio.DBusCallFlags.NONE,
                    1000,
                    None,
                )
                resumed += 1
            except GLib.Error:
                continue
    except GLib.Error:
        pass
    return resumed


def format_duration(seconds: float, language: str = "ru") -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} sec" if language == "en" else f"{seconds} сек"
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    if hours:
        return f"{hours} h {minutes:02d} min" if language == "en" else f"{hours} ч {minutes:02d} мин"
    return f"{minutes} min" if language == "en" else f"{minutes} мин"


def format_precise_duration(seconds: float, language: str = "ru") -> str:
    value = max(0, int(seconds))
    if value < 60:
        return f"{value} sec" if language == "en" else f"{value} сек"
    minutes, remainder = divmod(value, 60)
    if language == "en":
        return f"{minutes} min {remainder} sec" if remainder else f"{minutes} min"
    return f"{minutes} мин {remainder} сек" if remainder else f"{minutes} мин"


def snooze_button_text(minutes: int, language: str = "ru") -> str:
    value = max(1, min(20, int(minutes)))
    if language == "en":
        return f"Remind me in {value} min"
    if value == 1:
        return "Напомнить через 1 минуту"
    if 2 <= value <= 4:
        return f"Напомнить через {value} минуты"
    return f"Напомнить через {value} минут"


def notification_badge_text(unread: int) -> str:
    unread = max(0, int(unread))
    return "9+" if unread > 9 else str(unread)


def ensure_expanded_system_notifications() -> None:
    """Ask GNOME to display this application's notification body in banners."""
    source = Gio.SettingsSchemaSource.get_default()
    if not source or not source.lookup("org.gnome.desktop.notifications.application", True):
        return
    try:
        settings = Gio.Settings.new_with_path(
            "org.gnome.desktop.notifications.application",
            "/org/gnome/desktop/notifications/application/io-github-jabka-zdorovo/",
        )
        if not settings.get_boolean("force-expanded"):
            settings.set_boolean("force-expanded", True)
    except GLib.Error:
        return


def breathing_phase(preset: dict[str, Any], elapsed: float) -> tuple[str, float]:
    if elapsed <= 0:
        return "ready", 0.0
    inhale = max(1.0, float(preset["inhale"]))
    exhale = max(1.0, float(preset["exhale"]))
    within = elapsed % (inhale + exhale)
    if within < inhale:
        return "inhale", within / inhale
    return "exhale", (within - inhale) / exhale


def clear_box(box: Gtk.Box | Gtk.ListBox | Gtk.FlowBox) -> None:
    child = box.get_first_child()
    while child:
        next_child = child.get_next_sibling()
        box.remove(child)
        child = next_child


_ACTIVE_COLOR_THEME = "teal"
_PALETTE_TEXTURE_CACHE: dict[tuple[str, str, int], Gdk.Texture] = {}


def set_active_color_theme(color_theme: str) -> None:
    global _ACTIVE_COLOR_THEME
    normalized = normalize_color_theme(color_theme)
    if normalized != _ACTIVE_COLOR_THEME:
        _ACTIVE_COLOR_THEME = normalized
        _PALETTE_TEXTURE_CACHE.clear()


def render_palette_svg(svg: str, color_theme: str) -> str:
    accent = str(COLOR_PALETTES[normalize_color_theme(color_theme)]["accent_hex"])
    return re.sub(r"#327F79\b", accent, svg, flags=re.IGNORECASE)


def palette_icon_image(kind: str, size: int) -> Gtk.Image:
    """Load an SVG using the active palette instead of its teal source colour."""
    path = ASSET_ROOT / "icons" / f"{kind}.svg"
    cache_key = (_ACTIVE_COLOR_THEME, kind, size)
    texture = _PALETTE_TEXTURE_CACHE.get(cache_key)
    if texture is None:
        try:
            svg = path.read_text(encoding="utf-8")
            svg = render_palette_svg(svg, _ACTIVE_COLOR_THEME)
            texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(svg.encode("utf-8")))
            _PALETTE_TEXTURE_CACHE[cache_key] = texture
        except (GLib.Error, OSError):
            image = Gtk.Image.new_from_file(str(path))
            image.set_pixel_size(size)
            return image
    image = Gtk.Image.new_from_paintable(texture)
    image.set_pixel_size(size)
    return image


def activity_icon(kind: str, size: int = 25, css_class: str = "activity-icon-shell") -> Gtk.Widget:
    shell = Gtk.CenterBox(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, css_classes=[css_class])
    image = palette_icon_image(kind, size)
    shell.set_center_widget(image)
    return shell


def symbolic_icon(icon_name: str, size: int = 22, css_class: str = "settings-icon") -> Gtk.Widget:
    shell = Gtk.CenterBox(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, css_classes=[css_class])
    image = Gtk.Image.new_from_icon_name(icon_name)
    image.set_pixel_size(size)
    shell.set_center_widget(image)
    return shell


def status_banner(title: str) -> Gtk.Revealer:
    revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN)
    surface = Gtk.CenterBox(css_classes=["status-banner"])
    surface.set_center_widget(Gtk.Label(label=title, wrap=True, justify=Gtk.Justification.CENTER))
    revealer.set_child(surface)
    return revealer


def set_status_banner_state(revealer: Gtk.Revealer, visible: bool) -> None:
    """Hide inactive revealers completely so Gtk.Box does not reserve spacing."""
    revealer.set_reveal_child(visible)
    revealer.set_visible(visible)


ACHIEVEMENT_LEVEL_MARKS = ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X")


def achievement_level_mark(level: int) -> str:
    return ACHIEVEMENT_LEVEL_MARKS[level - 1] if 1 <= level <= len(ACHIEVEMENT_LEVEL_MARKS) else str(level)


def achievement_unlock_body(achievement: dict[str, Any], language: str) -> str:
    level = achievement_level_mark(int(achievement["level"]))
    title = str(achievement[f"title_{language}"])
    if language == "en":
        return f"You reached Level {level} in {title}."
    return f"Открыт уровень {level} в серии «{title}»."


def notification_body_for_display(kind: str, body: str, language: str) -> str:
    """Make compact achievement messages from older databases readable."""
    if kind != "achievement" or " · " not in body:
        return body
    title, level = (part.strip() for part in body.rsplit(" · ", 1))
    if not title or not level:
        return body
    if language == "en":
        return f"You reached Level {level} in {title}."
    return f"Открыт уровень {level} в серии «{title}»."


def achievement_emblem(icon: str, tone: str, level: int, unlocked: bool) -> Gtk.Widget:
    emblem = Gtk.Overlay(
        halign=Gtk.Align.CENTER,
        valign=Gtk.Align.CENTER,
        css_classes=[
            "achievement-emblem",
            f"achievement-{tone}",
            "unlocked" if unlocked else "locked",
        ],
    )
    ring = Gtk.CenterBox(css_classes=["achievement-emblem-ring"])
    ring.set_size_request(72, 72)
    image = palette_icon_image(icon, 34)
    ring.set_center_widget(image)
    emblem.set_child(ring)
    seal = Gtk.CenterBox(
        halign=Gtk.Align.END,
        valign=Gtk.Align.END,
        css_classes=["achievement-seal"],
    )
    seal.set_size_request(23, 23)
    seal_icon = Gtk.Label(
        label=achievement_level_mark(int(level)),
        css_classes=["achievement-level-mark"],
    )
    seal.set_center_widget(seal_icon)
    emblem.add_overlay(seal)
    return emblem


def cyberjabka_footer(*css_classes: str) -> Gtk.Label:
    footer = Gtk.Label(css_classes=["app-footer", *css_classes])
    footer.set_markup('<a href="https://cyberjabka.by/">© CYBERJABKA</a>')
    footer.set_tooltip_text("https://cyberjabka.by/")
    return footer


class LiquidGlassBackdrop(Gtk.DrawingArea):
    """Static, inexpensive color field that gives translucent controls visual depth."""

    def __init__(self, dark: bool = False, color_theme: str = "teal") -> None:
        super().__init__()
        self.dark = dark
        self.color_theme = normalize_color_theme(color_theme)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_draw_func(self._draw)

    def set_dark(self, dark: bool) -> None:
        self.dark = dark
        self.queue_draw()

    def set_color_theme(self, color_theme: str) -> None:
        self.color_theme = normalize_color_theme(color_theme)
        self.queue_draw()

    def _draw(self, _area: Gtk.DrawingArea, cr: Any, width: int, height: int) -> None:
        palette = COLOR_PALETTES[self.color_theme]
        cr.set_source_rgb(*(palette["backdrop_dark"] if self.dark else palette["backdrop_light"]))
        cr.paint()


class BreathingOrb(Gtk.DrawingArea):
    """Lightweight paced-breathing visual: the solid orb grows and recedes."""

    def __init__(self, color_theme: str = "teal") -> None:
        super().__init__(css_classes=["breathing-orb"])
        self.color_theme = normalize_color_theme(color_theme)
        self.phase = "ready"
        self.phase_progress = 0.0
        self.session_progress = 0.0
        self.set_content_width(250)
        self.set_content_height(250)
        self.set_draw_func(self._draw)

    def set_color_theme(self, color_theme: str) -> None:
        self.color_theme = normalize_color_theme(color_theme)
        self.queue_draw()

    def set_state(self, phase: str, phase_progress: float, session_progress: float) -> None:
        self.phase = phase
        self.phase_progress = max(0.0, min(1.0, phase_progress))
        self.session_progress = max(0.0, min(1.0, session_progress))
        self.queue_draw()

    def _draw(self, _area: Gtk.DrawingArea, cr: Any, width: int, height: int) -> None:
        palette = COLOR_PALETTES[self.color_theme]
        accent = palette["accent"]
        accent_light = palette["accent_light"]
        cx, cy = width / 2, height / 2
        outer = min(width, height) * 0.39
        for index in range(32):
            angle = math.tau * index / 32 - math.pi / 2
            inner_tick = outer + 9
            outer_tick = outer + (14 if index % 4 == 0 else 12)
            cr.set_line_width(1.5 if index % 4 == 0 else 1)
            cr.set_source_rgba(1, 1, 1, 0.26 if index % 4 == 0 else 0.12)
            cr.move_to(cx + math.cos(angle) * inner_tick, cy + math.sin(angle) * inner_tick)
            cr.line_to(cx + math.cos(angle) * outer_tick, cy + math.sin(angle) * outer_tick)
            cr.stroke()
        cr.set_line_width(2)
        cr.set_source_rgba(1, 1, 1, 0.18)
        cr.arc(cx, cy, outer, 0, math.tau)
        cr.stroke()
        cr.set_line_width(4)
        cr.set_line_cap(1)
        cr.set_source_rgb(*accent_light)
        cr.arc(cx, cy, outer, -math.pi / 2, -math.pi / 2 + math.tau * self.session_progress)
        cr.stroke()
        if self.phase == "inhale":
            size_factor = 0.58 + 0.36 * self.phase_progress
        elif self.phase == "exhale":
            size_factor = 0.94 - 0.36 * self.phase_progress
        else:
            size_factor = 0.62
        radius = outer * size_factor
        cr.set_source_rgba(*accent, 0.22)
        cr.arc(cx, cy, radius + 14, 0, math.tau)
        cr.fill()
        cr.set_source_rgb(*accent)
        cr.arc(cx, cy, radius, 0, math.tau)
        cr.fill()


class BlurredWallpaper(Gtk.Widget):
    """A local, non-captured frosted backdrop built from the current GNOME wallpaper."""

    def __init__(self, dark: bool) -> None:
        super().__init__()
        self.dark = dark
        self.texture: Gdk.Texture | None = None
        self.set_hexpand(True)
        self.set_vexpand(True)
        try:
            uri = Gio.Settings.new("org.gnome.desktop.background").get_string("picture-uri")
            path = Gio.File.new_for_uri(uri).get_path() if uri else None
            if path and Path(path).is_file():
                self.texture = Gdk.Texture.new_from_filename(path)
        except (GLib.Error, OSError):
            self.texture = None

    @staticmethod
    def _color(value: str) -> Gdk.RGBA:
        color = Gdk.RGBA()
        color.parse(value)
        return color

    def do_snapshot(self, snapshot: Gtk.Snapshot) -> None:
        width, height = float(self.get_width()), float(self.get_height())
        if width <= 0 or height <= 0:
            return
        bounds = Graphene.Rect().init(0, 0, width, height)
        snapshot.append_color(self._color("#171419" if self.dark else "#302a31"), bounds)
        if self.texture:
            texture_w, texture_h = self.texture.get_width(), self.texture.get_height()
            # Blur samples outside its source. Overscan keeps transparent pixels away
            # from the physical screen edge and prevents a pale halo there.
            overscan = 96.0
            scale = max((width + overscan * 2) / texture_w, (height + overscan * 2) / texture_h)
            draw_w, draw_h = texture_w * scale, texture_h * scale
            image_bounds = Graphene.Rect().init((width - draw_w) / 2, (height - draw_h) / 2, draw_w, draw_h)
            snapshot.push_blur(34.0)
            snapshot.append_texture(self.texture, image_bounds)
            snapshot.pop()
        snapshot.append_color(
            self._color("rgba(20,16,22,0.58)" if self.dark else "rgba(38,28,36,0.34)"),
            bounds,
        )


CHART_COLORS = (
    (0.196, 0.498, 0.475),
    (0.184, 0.455, 0.735),
    (0.129, 0.584, 0.486),
    (0.878, 0.525, 0.153),
    (0.467, 0.337, 0.741),
    (0.365, 0.455, 0.525),
)

BREATHING_PRESETS: dict[str, dict[str, Any]] = {
    "gentle": {
        "title": "Мягкий старт",
        "duration": 120,
        "inhale": 3,
        "exhale": 4,
        "description": "Спокойный короткий ритм без задержки дыхания",
    },
    "calm": {
        "title": "Спокойный ритм",
        "duration": 300,
        "inhale": 4,
        "exhale": 6,
        "description": "Пять минут с немного более длинным выдохом",
    },
    "equal": {
        "title": "Ровное дыхание",
        "duration": 180,
        "inhale": 4,
        "exhale": 4,
        "description": "Одинаковая длительность вдоха и выдоха",
    },
}


class ColorSwatch(Gtk.DrawingArea):
    def __init__(self, color: tuple[float, float, float], size: int = 12) -> None:
        super().__init__()
        self.color = color
        self.set_content_width(size)
        self.set_content_height(size)
        self.set_draw_func(self._draw)

    def set_color(self, color: tuple[float, float, float]) -> None:
        self.color = color
        self.queue_draw()

    def _draw(self, _area: Gtk.DrawingArea, cr: Any, width: int, height: int) -> None:
        cr.set_source_rgb(*self.color)
        cr.arc(width / 2, height / 2, min(width, height) / 2, 0, math.tau)
        cr.fill()


class PaletteEmblem(Gtk.DrawingArea):
    """Small fan of colour cards used beside the palette selector."""

    def __init__(self, color_theme: str) -> None:
        super().__init__(css_classes=["palette-emblem"])
        self.color_theme = normalize_color_theme(color_theme)
        self.set_content_width(40)
        self.set_content_height(40)
        self.set_draw_func(self._draw)

    def _draw(self, _area: Gtk.DrawingArea, cr: Any, width: int, height: int) -> None:
        palette = COLOR_PALETTES[self.color_theme]
        accent = palette["accent"]
        light = palette["accent_light"]
        middle = tuple((left + right) / 2 for left, right in zip(accent, light, strict=True))
        pivot_x, pivot_y = width / 2, height * 0.72
        for angle, color in zip((-0.38, 0.0, 0.38), (light, middle, accent), strict=True):
            cr.save()
            cr.translate(pivot_x, pivot_y)
            cr.rotate(angle)
            rounded_rect(cr, -4.5, -23, 9, 25, 3)
            cr.set_source_rgba(*color, 0.96)
            cr.fill_preserve()
            cr.set_source_rgba(1, 1, 1, 0.5)
            cr.set_line_width(1)
            cr.stroke()
            cr.restore()
        cr.set_source_rgb(*light)
        cr.arc(pivot_x, pivot_y, 3.4, 0, math.tau)
        cr.fill()
        cr.set_source_rgb(*accent)
        cr.arc(pivot_x, pivot_y, 1.6, 0, math.tau)
        cr.fill()


class WeekChart(Gtk.DrawingArea):
    def __init__(self, db: UsageDatabase, language: str = "ru") -> None:
        super().__init__()
        self.db = db
        self.language = language
        self.categories: list[dict[str, Any]] = []
        self.hidden: set[str] = set()
        self._hits: list[dict[str, Any]] = []
        self._hovered: dict[str, Any] | None = None
        self._pointer = (0.0, 0.0)
        self.set_content_height(230)
        self.set_hexpand(True)
        self.set_has_tooltip(False)
        self.set_draw_func(self._draw)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._motion)
        motion.connect("leave", self._leave)
        self.add_controller(motion)

    def set_categories(self, categories: list[dict[str, Any]], hidden: set[str]) -> None:
        self.categories = categories
        self.hidden = hidden
        self._hovered = None
        self.queue_draw()

    def _series(self) -> list[tuple[str, list[tuple[dict[str, Any], float]]]]:
        start = datetime.now().date() - timedelta(days=6)
        days: dict[str, dict[str, float]] = {(start + timedelta(days=i)).isoformat(): {} for i in range(7)}
        names = {category["app_id"] for category in self.categories if category["app_id"] != "__other__"}
        has_other = any(category["app_id"] == "__other__" for category in self.categories)
        for row in self.db.daily_app_totals(7):
            app_id = str(row["app_id"])
            target = app_id if app_id in names else "__other__"
            if target == "__other__" and not has_other:
                continue
            day = str(row["day"])
            days.setdefault(day, {})[target] = days.setdefault(day, {}).get(target, 0.0) + float(
                row["seconds"]
            )
        return [
            (
                day,
                [
                    (category, values.get(category["app_id"], 0.0))
                    for category in self.categories
                    if category["app_id"] not in self.hidden
                ],
            )
            for day, values in days.items()
        ]

    def _short_duration(self, seconds: float) -> str:
        minutes = int(seconds // 60)
        if minutes >= 60:
            hours, rest = divmod(minutes, 60)
            suffix_h, suffix_m = ("h", "m") if self.language == "en" else ("ч", "м")
            return f"{hours}{suffix_h} {rest:02d}{suffix_m}" if rest else f"{hours}{suffix_h}"
        if minutes:
            return f"{minutes}{'m' if self.language == 'en' else 'м'}"
        return f"{max(0, int(seconds))}{'s' if self.language == 'en' else 'с'}"

    def _motion(self, _controller: Gtk.EventControllerMotion, x: float, y: float) -> None:
        self._pointer = (x, y)
        hovered = next(
            (hit for hit in self._hits if hit["x1"] <= x <= hit["x2"] and hit["y1"] <= y <= hit["y2"]), None
        )
        if hovered is not self._hovered:
            self._hovered = hovered
            self.queue_draw()

    def _leave(self, _controller: Gtk.EventControllerMotion) -> None:
        if self._hovered:
            self._hovered = None
            self.queue_draw()

    def _draw(self, _area: Gtk.DrawingArea, cr: Any, width: int, height: int) -> None:
        data = self._series()
        totals = [sum(value for _category, value in values) for _day, values in data]
        max_value = max(totals, default=1) or 1
        left, right, top, bottom = 22, 12, 34, 30
        chart_w, chart_h = width - left - right, height - top - bottom
        dark = Adw.StyleManager.get_default().get_dark()
        cr.set_source_rgba(1, 1, 1, 0.09 if dark else 0.52)
        for i in range(4):
            y = top + chart_h * i / 3
            cr.rectangle(left, y, chart_w, 1)
            cr.fill()
        slot = chart_w / 7
        bar_w = max(38, min(64, slot * 0.76))
        cr.save()
        cr.set_dash([2.0, 5.0])
        cr.set_line_width(1)
        cr.set_source_rgba(1, 1, 1, 0.07) if dark else cr.set_source_rgba(0.30, 0.27, 0.38, 0.075)
        for boundary in range(1, 7):
            separator_x = left + slot * boundary
            cr.move_to(separator_x, top + 4)
            cr.line_to(separator_x, top + chart_h - 3)
        cr.stroke()
        cr.restore()
        self._hits = []
        for index, ((day, values), total) in enumerate(zip(data, totals, strict=False)):
            x = left + slot * index + (slot - bar_w) / 2
            total_h = chart_h * total / max_value
            base_y = top + chart_h
            if total > 0:
                cr.save()
                rounded_rect(cr, x, base_y - total_h, bar_w, max(total_h, 3), 7)
                cr.clip()
                cursor = base_y
                for category, value in values:
                    if value <= 0:
                        continue
                    segment_h = total_h * value / total
                    y = cursor - segment_h
                    cr.set_source_rgb(*category["color"])
                    cr.rectangle(x, y, bar_w, segment_h + 0.5)
                    cr.fill()
                    self._hits.append(
                        {
                            "x1": x,
                            "x2": x + bar_w,
                            "y1": y,
                            "y2": cursor,
                            "day": day,
                            "name": category["name"],
                            "seconds": value,
                        }
                    )
                    cursor = y
                cr.restore()

                cr.set_source_rgba(0.93, 0.90, 0.91, 1) if dark else cr.set_source_rgba(0.28, 0.25, 0.33, 1)
                cr.select_font_face("Sans", 0, 1)
                cr.set_font_size(10)
                total_text = self._short_duration(total)
                ext = cr.text_extents(total_text)
                cr.move_to(x + bar_w / 2 - ext.width / 2, max(12, base_y - total_h - 7))
                cr.show_text(total_text)

            day_labels = (
                ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
                if self.language == "en"
                else ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
            )
            label = day_labels[datetime.fromisoformat(day).weekday()]
            cr.set_source_rgba(0.76, 0.72, 0.74, 1) if dark else cr.set_source_rgba(0.42, 0.39, 0.49, 1)
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(10)
            ext = cr.text_extents(label)
            cr.move_to(x + bar_w / 2 - ext.width / 2, height - 9)
            cr.show_text(label)

        if self._hovered:
            hit = self._hovered
            name_text = str(hit["name"])
            day_suffix = "on this day" if self.language == "en" else "в этот день"
            time_text = f"{format_duration(float(hit['seconds']), self.language)} {day_suffix}"
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(10)
            name_ext = cr.text_extents(name_text)
            cr.select_font_face("Sans", 0, 1)
            cr.set_font_size(12)
            time_ext = cr.text_extents(time_text)
            box_w, box_h = max(name_ext.width, time_ext.width) + 24, 48
            px, py = self._pointer
            tx = min(max(6, px - box_w / 2), width - box_w - 6)
            ty = max(5, py - box_h - 12)
            cr.set_source_rgb(*COLOR_PALETTES[_ACTIVE_COLOR_THEME]["accent"])
            rounded_rect(cr, tx, ty, box_w, box_h, 7)
            cr.fill()
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(10)
            cr.set_source_rgba(1, 1, 1, 0.78)
            cr.move_to(tx + 12, ty + 17)
            cr.show_text(name_text)
            cr.select_font_face("Sans", 0, 1)
            cr.set_font_size(12)
            cr.set_source_rgb(1, 1, 1)
            cr.move_to(tx + 12, ty + 36)
            cr.show_text(time_text)


class WellnessChart(Gtk.DrawingArea):
    SERIES = (
        ("headache", (0.69, 0.17, 0.21)),
        ("eyes", (0.20, 0.47, 0.76)),
        ("neck", (0.42, 0.27, 0.68)),
        ("back", (0.89, 0.48, 0.12)),
    )

    def __init__(self, db: UsageDatabase, language: str = "ru") -> None:
        super().__init__()
        self.db = db
        self.language = language
        self.set_content_height(210)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def _draw(self, _area: Gtk.DrawingArea, cr: Any, width: int, height: int) -> None:
        data = self.db.wellness_days(7)
        dark = Adw.StyleManager.get_default().get_dark()
        left, right, top, bottom = 34, 14, 18, 30
        chart_w, chart_h = width - left - right, height - top - bottom
        for score in (0, 5, 10):
            y = top + chart_h * (10 - score) / 10
            cr.set_source_rgba(1, 1, 1, 0.10) if dark else cr.set_source_rgba(0.28, 0.25, 0.38, 0.10)
            cr.rectangle(left, y, chart_w, 1)
            cr.fill()
            cr.set_source_rgba(0.78, 0.74, 0.77, 0.75) if dark else cr.set_source_rgba(0.42, 0.39, 0.49, 0.72)
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(9)
            cr.move_to(6, y + 3)
            cr.show_text(str(score))

        slot = chart_w / 7
        max_screen = max((float(item["screen_seconds"]) for item in data), default=1) or 1
        for index, item in enumerate(data):
            screen_h = chart_h * 0.36 * float(item["screen_seconds"]) / max_screen
            x = left + slot * index + slot * 0.22
            if screen_h > 0:
                cr.set_source_rgba(1, 1, 1, 0.08) if dark else cr.set_source_rgba(0.30, 0.28, 0.40, 0.055)
                rounded_rect(cr, x, top + chart_h - screen_h, slot * 0.56, screen_h, 4)
                cr.fill()

        for key, color in self.SERIES:
            points: list[tuple[float, float]] = []
            for index, item in enumerate(data):
                value = item[key]
                if value is None:
                    continue
                points.append((left + slot * (index + 0.5), top + chart_h * (10 - float(value)) / 10))
            if not points:
                continue
            cr.set_source_rgb(*color)
            cr.set_line_width(2.4)
            for index, (x, y) in enumerate(points):
                if index == 0:
                    cr.move_to(x, y)
                else:
                    cr.line_to(x, y)
            cr.stroke()
            for x, y in points:
                cr.set_source_rgb(*color)
                cr.arc(x, y, 4.2, 0, math.tau)
                cr.fill()
                cr.set_source_rgb(0.15, 0.13, 0.18) if dark else cr.set_source_rgb(1, 1, 1)
                cr.arc(x, y, 1.7, 0, math.tau)
                cr.fill()

        day_names = (
            ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
            if self.language == "en"
            else ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
        )
        for index, item in enumerate(data):
            label = day_names[datetime.fromisoformat(str(item["day"])).weekday()]
            cr.set_source_rgba(0.77, 0.73, 0.76, 1) if dark else cr.set_source_rgba(0.42, 0.39, 0.49, 1)
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(9)
            ext = cr.text_extents(label)
            x = left + slot * (index + 0.5)
            cr.move_to(x - ext.width / 2, height - 8)
            cr.show_text(label)


class DayActivityChart(Gtk.DrawingArea):
    def __init__(self, db: UsageDatabase, day: str, language: str = "ru") -> None:
        super().__init__()
        self.db = db
        self.day = day
        self.language = language
        self.categories: list[dict[str, Any]] = []
        self.hidden: set[str] = set()
        self._hits: list[dict[str, Any]] = []
        self._hovered: dict[str, Any] | None = None
        self._pointer = (0.0, 0.0)
        self.set_content_width(1440)
        self.set_content_height(276)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._motion)
        motion.connect("leave", self._leave)
        self.add_controller(motion)

    def set_day(self, day: str) -> None:
        self.day = day
        self._hovered = None
        self.queue_draw()

    def set_categories(self, categories: list[dict[str, Any]], hidden: set[str]) -> None:
        self.categories = categories
        self.hidden = hidden
        self._hovered = None
        self.queue_draw()

    def _bins(self) -> list[list[tuple[dict[str, Any], float]]]:
        values: list[dict[str, float]] = [{} for _ in range(24)]
        direct = {category["app_id"] for category in self.categories if category["app_id"] != "__other__"}
        has_other = any(category["app_id"] == "__other__" for category in self.categories)
        for row in self.db.hourly_app_totals(self.day):
            app_id = str(row["app_id"])
            target = app_id if app_id in direct else "__other__"
            if target == "__other__" and not has_other:
                continue
            time_bin = int(row["hour"])
            values[time_bin][target] = values[time_bin].get(target, 0.0) + float(row["seconds"])
        return [
            [
                (category, hour.get(category["app_id"], 0.0))
                for category in self.categories
                if category["app_id"] not in self.hidden
            ]
            for hour in values
        ]

    def _motion(self, _controller: Gtk.EventControllerMotion, x: float, y: float) -> None:
        self._pointer = (x, y)
        hovered = next(
            (
                hit
                for hit in reversed(self._hits)
                if hit["x1"] <= x <= hit["x2"] and hit["y1"] <= y <= hit["y2"]
            ),
            None,
        )
        if hovered is not self._hovered:
            self._hovered = hovered
            self.queue_draw()

    def _leave(self, _controller: Gtk.EventControllerMotion) -> None:
        self._hovered = None
        self.queue_draw()

    def _draw(self, _area: Gtk.DrawingArea, cr: Any, width: int, height: int) -> None:
        bins = self._bins()
        totals = [sum(value for _category, value in values) for values in bins]
        max_value = max(totals, default=1) or 1
        left, right, top, bottom = 20, 12, 40, 40
        chart_w, chart_h = width - left - right, height - top - bottom
        dark = Adw.StyleManager.get_default().get_dark()
        for index in range(4):
            y = top + chart_h * index / 3
            cr.set_source_rgba(1, 1, 1, 0.08) if dark else cr.set_source_rgba(0.30, 0.27, 0.38, 0.08)
            cr.rectangle(left, y, chart_w, 1)
            cr.fill()
        slot = chart_w / 24
        bar_w = max(38, min(64, slot * 0.76))
        cr.save()
        cr.set_dash([2.0, 5.0])
        cr.set_line_width(1)
        cr.set_source_rgba(1, 1, 1, 0.055) if dark else cr.set_source_rgba(0.30, 0.27, 0.38, 0.055)
        for boundary in range(1, 24):
            separator_x = left + slot * boundary
            cr.move_to(separator_x, top + 4)
            cr.line_to(separator_x, top + chart_h - 3)
        cr.stroke()
        cr.restore()
        self._hits = []
        for time_bin, (segments, total) in enumerate(zip(bins, totals, strict=False)):
            start_hour = time_bin
            x = left + slot * time_bin + (slot - bar_w) / 2
            total_h = chart_h * total / max_value
            base_y = top + chart_h
            if total > 0:
                cr.save()
                rounded_rect(cr, x, base_y - total_h, bar_w, max(3, total_h), 4)
                cr.clip()
                cursor = base_y
                for category, value in segments:
                    if value <= 0:
                        continue
                    segment_h = total_h * value / total
                    y = cursor - segment_h
                    cr.set_source_rgb(*category["color"])
                    cr.rectangle(x, y, bar_w, segment_h + 0.5)
                    cr.fill()
                    self._hits.append(
                        {
                            "x1": x,
                            "x2": x + bar_w,
                            "y1": y,
                            "y2": cursor,
                            "hour": start_hour,
                            "name": category["name"],
                            "seconds": value,
                        }
                    )
                    cursor = y
                cr.restore()
                total_label = self._compact_duration(total)
                cr.select_font_face("Sans", 0, 1)
                cr.set_font_size(11)
                total_ext = cr.text_extents(total_label)
                label_x = x + bar_w / 2 - total_ext.width / 2
                label_y = max(18, base_y - total_h - 10)
                cr.set_source_rgba(0.12, 0.11, 0.14, 0.76) if dark else cr.set_source_rgba(1, 1, 1, 0.88)
                rounded_rect(cr, label_x - 5, label_y - 13, total_ext.width + 10, 18, 6)
                cr.fill()
                cr.set_source_rgba(0.96, 0.93, 0.94, 1) if dark else cr.set_source_rgba(0.23, 0.21, 0.29, 1)
                cr.move_to(label_x, label_y)
                cr.show_text(total_label)
            label = f"{start_hour:02d}"
            cr.set_source_rgba(0.76, 0.72, 0.74, 1) if dark else cr.set_source_rgba(0.42, 0.39, 0.49, 1)
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(10)
            ext = cr.text_extents(label)
            cr.move_to(x + bar_w / 2 - ext.width / 2, height - 14)
            cr.show_text(label)
        if self._hovered:
            hit = self._hovered
            hour_text = f"{hit['hour']:02d}:00–{(hit['hour'] + 1):02d}:00"
            detail = f"{hit['name']} · {format_duration(hit['seconds'], self.language)}"
            cr.select_font_face("Sans", 0, 1)
            cr.set_font_size(11)
            detail_ext = cr.text_extents(detail)
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(9)
            hour_ext = cr.text_extents(hour_text)
            box_w, box_h = max(detail_ext.width, hour_ext.width) + 22, 45
            px, py = self._pointer
            tx = min(max(5, px - box_w / 2), width - box_w - 5)
            ty = max(4, py - box_h - 10)
            cr.set_source_rgb(*COLOR_PALETTES[_ACTIVE_COLOR_THEME]["accent"])
            rounded_rect(cr, tx, ty, box_w, box_h, 7)
            cr.fill()
            cr.set_source_rgba(1, 1, 1, 0.75)
            cr.move_to(tx + 11, ty + 16)
            cr.show_text(hour_text)
            cr.select_font_face("Sans", 0, 1)
            cr.set_font_size(11)
            cr.set_source_rgb(1, 1, 1)
            cr.move_to(tx + 11, ty + 34)
            cr.show_text(detail)

    def _compact_duration(self, seconds: float) -> str:
        minutes = max(0, int(round(seconds / 60)))
        if minutes >= 60:
            hours, remainder = divmod(minutes, 60)
            if self.language == "en":
                return f"{hours}h {remainder:02d}m" if remainder else f"{hours}h"
            return f"{hours}ч {remainder:02d}м" if remainder else f"{hours}ч"
        return f"{minutes}{'m' if self.language == 'en' else 'м'}"


def rounded_rect(cr: Any, x: float, y: float, w: float, h: float, radius: float) -> None:
    radius = min(radius, w / 2, h / 2)
    cr.new_sub_path()
    cr.arc(x + w - radius, y + radius, radius, -math.pi / 2, 0)
    cr.arc(x + w - radius, y + h - radius, radius, 0, math.pi / 2)
    cr.arc(x + radius, y + h - radius, radius, math.pi / 2, math.pi)
    cr.arc(x + radius, y + radius, radius, math.pi, 3 * math.pi / 2)
    cr.close_path()


class DateRangeCalendar(Gtk.Box):
    """A compact month calendar with two-click range selection and hover preview."""

    def __init__(
        self,
        language: str,
        start: date,
        end: date,
        minimum: date,
        maximum: date,
        on_selected: Callable[[date, date], None],
        range_selection: bool = True,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["range-calendar"])
        self.language = language
        self.start = min(start, end)
        self.end = max(start, end)
        self.minimum = minimum
        self.maximum = maximum
        self.on_selected = on_selected
        self.range_selection = range_selection
        self.pending_start: date | None = None
        self.hover_day: date | None = None
        self.display_month = self.end.replace(day=1)
        self.day_buttons: dict[date, Gtk.Button] = {}

        header = Gtk.Box(spacing=4, css_classes=["range-calendar-header"])
        self.previous_month = Gtk.Button(icon_name="go-previous-symbolic", css_classes=["range-month-button"])
        self.previous_month.connect("clicked", self._shift_month, -1)
        self.month_label = Gtk.Label(hexpand=True, css_classes=["range-month-title"])
        self.next_month = Gtk.Button(icon_name="go-next-symbolic", css_classes=["range-month-button"])
        self.next_month.connect("clicked", self._shift_month, 1)
        header.append(self.previous_month)
        header.append(self.month_label)
        header.append(self.next_month)
        self.append(header)

        self.grid = Gtk.Grid(
            column_homogeneous=True, row_homogeneous=True, css_classes=["range-calendar-grid"]
        )
        self.grid.set_halign(Gtk.Align.CENTER)
        self.append(self.grid)
        self.hint = Gtk.Label(
            xalign=0,
            wrap=True,
            max_width_chars=24,
            css_classes=["range-calendar-hint"],
        )
        self.append(self.hint)
        self._rebuild()

    @staticmethod
    def _month_start(value: date) -> date:
        return value.replace(day=1)

    @staticmethod
    def _add_month(value: date, offset: int) -> date:
        absolute = value.year * 12 + value.month - 1 + offset
        return date(absolute // 12, absolute % 12 + 1, 1)

    def set_range(self, start: date, end: date, show_end_month: bool = False) -> None:
        self.start, self.end = sorted((start, end))
        self.pending_start = None
        self.hover_day = None
        if show_end_month:
            self.display_month = self.end.replace(day=1)
        self._rebuild()

    def _shift_month(self, _button: Gtk.Button, offset: int) -> None:
        target = self._add_month(self.display_month, offset)
        if target < self.minimum.replace(day=1) or target > self.maximum.replace(day=1):
            return
        self.display_month = target
        self._rebuild()

    def _on_day_enter(
        self, _controller: Gtk.EventControllerMotion, _x: float, _y: float, target: date
    ) -> None:
        if self.pending_start is None or target == self.hover_day:
            return
        self.hover_day = target
        self._render_range()

    def _on_day_clicked(self, _button: Gtk.Button, target: date) -> None:
        if not self.range_selection:
            self.start = target
            self.end = target
            self.pending_start = None
            self.hover_day = None
            self._render_range()
            self.on_selected(target, target)
            return
        if self.pending_start is None:
            self.pending_start = target
            self.hover_day = target
            self._render_range()
            return
        self.start, self.end = sorted((self.pending_start, target))
        self.pending_start = None
        self.hover_day = None
        self._render_range()
        self.on_selected(self.start, self.end)

    def _rebuild(self) -> None:
        clear_box(self.grid)
        self.day_buttons.clear()
        months_en = (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        )
        months_ru = (
            "Январь",
            "Февраль",
            "Март",
            "Апрель",
            "Май",
            "Июнь",
            "Июль",
            "Август",
            "Сентябрь",
            "Октябрь",
            "Ноябрь",
            "Декабрь",
        )
        months = months_en if self.language == "en" else months_ru
        self.month_label.set_text(f"{months[self.display_month.month - 1]} {self.display_month.year}")
        weekdays = (
            ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")
            if self.language == "en"
            else (
                "Пн",
                "Вт",
                "Ср",
                "Чт",
                "Пт",
                "Сб",
                "Вс",
            )
        )
        for column, weekday in enumerate(weekdays):
            self.grid.attach(Gtk.Label(label=weekday, css_classes=["range-weekday"]), column, 0, 1, 1)
        weeks = pycalendar.Calendar(firstweekday=0).monthdayscalendar(
            self.display_month.year, self.display_month.month
        )
        for row, week in enumerate(weeks, start=1):
            for column, day_number in enumerate(week):
                if not day_number:
                    self.grid.attach(Gtk.Label(label=""), column, row, 1, 1)
                    continue
                target = date(self.display_month.year, self.display_month.month, day_number)
                button = Gtk.Button(label=str(day_number), css_classes=["range-day"])
                enabled = self.minimum <= target <= self.maximum
                button.set_sensitive(enabled)
                if enabled:
                    button.connect("clicked", self._on_day_clicked, target)
                    motion = Gtk.EventControllerMotion()
                    motion.connect("enter", self._on_day_enter, target)
                    button.add_controller(motion)
                self.grid.attach(button, column, row, 1, 1)
                self.day_buttons[target] = button
        self.previous_month.set_sensitive(self.display_month > self.minimum.replace(day=1))
        self.next_month.set_sensitive(self.display_month < self.maximum.replace(day=1))
        self._render_range()

    def _render_range(self) -> None:
        previewing = self.pending_start is not None
        first = self.pending_start if previewing else self.start
        last = (self.hover_day or self.pending_start) if previewing else self.end
        if first is None or last is None:
            return
        range_start, range_end = sorted((first, last))
        for target, button in self.day_buttons.items():
            for css_class in ("range-inside", "range-start", "range-end", "range-preview"):
                button.remove_css_class(css_class)
            if range_start <= target <= range_end:
                button.add_css_class("range-inside")
                if previewing:
                    button.add_css_class("range-preview")
            if target == range_start:
                button.add_css_class("range-start")
            if target == range_end:
                button.add_css_class("range-end")
        if not self.range_selection:
            self.hint.set_text("Choose a day" if self.language == "en" else "Выберите день")
        elif previewing:
            self.hint.set_text(
                "Now choose the last day" if self.language == "en" else "Теперь выберите конец"
            )
        else:
            self.hint.set_text("Choose the first day" if self.language == "en" else "Выберите начало")


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app: ZdorovoApplication) -> None:
        language = str(app.config.data.get("language", "en"))
        super().__init__(application=app, title="Zdorovo" if language == "en" else APP_NAME)
        self.set_icon_name(APP_ICON_NAME)
        self.language = language
        self.app = app
        self.analytics_day = datetime.now().date()
        today = datetime.now().date()
        earliest = min(today, app.db.earliest_usage_day())
        self.wellness_range_end = today
        self.wellness_range_start = max(earliest, today - timedelta(days=29))
        self.analytics_hidden_apps = set(app.config.data.get("analytics_hidden_apps", []))
        self.breathing_preset = "calm"
        self.breathing_elapsed = 0.0
        self.breathing_running = False
        self.breathing_last_tick = time.monotonic()
        self.breathing_timer_source: int | None = None
        self.training_duration_choice = int(app.config.data.get("training_duration_days", 30))
        self.training_fitness_choice = str(app.config.data.get("training_fitness_level", "beginner"))
        self.training_weekdays_choice = normalize_weekdays(
            app.config.data.get("training_weekdays"),
            int(app.config.data.get("training_days_per_week", 3)),
        )
        self.training_days_choice = len(self.training_weekdays_choice)
        active_training = app.db.active_training()
        self.training_course_choice = (
            str(active_training["course_id"]) if active_training else next(iter(COURSES))
        )
        saved_answers = {
            "full_body": ("balanced", "steady"),
            "upper_body": ("upper", "steady"),
            "legs": ("lower", "gentle"),
            "lower_body": ("lower", "strength"),
            "balance": ("mobility", "gentle"),
        }
        self.training_goal_choice, self.training_style_choice = saved_answers.get(
            self.training_course_choice,
            ("balanced", "steady"),
        )
        self.training_setup_step = 0
        self.training_view = "active" if active_training else "setup"
        self.training_calendar_month = date.today().replace(day=1)
        self.training_elapsed = 0.0
        self.training_running = False
        self.training_last_tick = time.monotonic()
        self.training_timer_source: int | None = None
        self.training_session_token: tuple[int, int] | None = None
        if app.config.data["dark_mode"]:
            self.add_css_class("dark-mode")
        self.set_default_size(1060, 720)
        self.set_size_request(780, 560)
        self.connect("close-request", self._on_close)
        self._build_window_content()

    def _build_window_content(self) -> None:
        app = self.app
        toolbar = Adw.ToolbarView()
        toolbar.add_css_class("glass-toolbar")
        header = Adw.HeaderBar()
        header.add_css_class("topbar")
        self._syncing_theme_control = False
        self.theme_switch = Gtk.Switch(valign=Gtk.Align.CENTER, active=app.config.data["dark_mode"])
        self.theme_switch.connect("notify::active", self._theme_changed)
        theme_box = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        self.theme_icon = Gtk.Image.new_from_icon_name(
            "weather-clear-night-symbolic" if app.config.data["dark_mode"] else "weather-clear-symbolic"
        )
        theme_box.append(self.theme_icon)
        self.theme_label = Gtk.Label()
        theme_box.append(self.theme_label)
        theme_box.append(self.theme_switch)
        header.pack_end(theme_box)
        self.sidebar_open_button = Gtk.Button(
            icon_name="sidebar-show-symbolic",
            tooltip_text="Show navigation" if self.language == "en" else "Показать меню",
            css_classes=["sidebar-header-button"],
        )
        self.sidebar_open_button.connect("clicked", self._show_sidebar)
        header.pack_start(self.sidebar_open_button)
        self.notification_button = Gtk.MenuButton(
            css_classes=["notification-button"],
            tooltip_text=self._t("Уведомления"),
        )
        bell_overlay = Gtk.Overlay()
        bell_icon = palette_icon_image("bell", 21)
        bell_overlay.set_child(bell_icon)
        self.notification_badge = Gtk.Label(
            label="0",
            halign=Gtk.Align.END,
            valign=Gtk.Align.START,
            css_classes=["notification-badge"],
        )
        bell_overlay.add_overlay(self.notification_badge)
        notification_title = Gtk.Box(spacing=6, css_classes=["notification-title-control"])
        notification_title.append(
            Gtk.Label(
                label="Zdorovo" if self.language == "en" else APP_NAME,
                css_classes=["app-title"],
            )
        )
        notification_title.append(
            Gtk.Separator(
                orientation=Gtk.Orientation.VERTICAL,
                css_classes=["notification-title-separator"],
            )
        )
        notification_title.append(bell_overlay)
        self.notification_button.set_child(notification_title)
        notification_popover = Gtk.Popover(css_classes=["notification-popover"])
        notification_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            css_classes=["notification-center"],
        )
        notification_head = Gtk.Box(spacing=8)
        notification_head.append(
            Gtk.Label(
                label=self._t("Уведомления"),
                xalign=0,
                hexpand=True,
                css_classes=["section-title"],
            )
        )
        mark_read = Gtk.Button(label=self._t("Прочитать все"), css_classes=["notification-read-all"])
        mark_read.connect("clicked", self._mark_notifications_read)
        notification_head.append(mark_read)
        notification_box.append(notification_head)
        notification_scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            css_classes=["notification-scroll"],
        )
        notification_scroll.set_max_content_height(420)
        notification_scroll.set_propagate_natural_height(True)
        self.notification_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        notification_scroll.set_child(self.notification_list)
        notification_box.append(notification_scroll)
        notification_popover.set_child(notification_box)
        self.notification_button.set_popover(notification_popover)
        self.notification_button.connect("notify::active", self._notification_popover_changed)
        header.set_title_widget(self.notification_button)
        toolbar.add_top_bar(header)

        split = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, css_classes=["main-split"])
        sidebar_wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["sidebar"])
        sidebar_wrap.set_size_request(205, -1)
        sidebar_wrap.set_hexpand(False)
        sidebar_head = Gtk.Box(spacing=8, css_classes=["sidebar-head"])
        sidebar_title = Gtk.Label(
            label=self._t("ВАШ РИТМ"),
            xalign=0,
            hexpand=True,
            css_classes=["sidebar-kicker"],
        )
        sidebar_head.append(sidebar_title)
        sidebar_close = Gtk.Button(
            icon_name="go-previous-symbolic",
            tooltip_text="Hide navigation" if self.language == "en" else "Скрыть меню",
            css_classes=["sidebar-close-button"],
        )
        sidebar_close.connect("clicked", self._hide_sidebar)
        sidebar_head.append(sidebar_close)
        sidebar_wrap.append(sidebar_head)
        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.NONE)
        self.stack.set_hhomogeneous(False)
        self.stack.set_vhomogeneous(False)
        sidebar = Gtk.StackSidebar(stack=self.stack, vexpand=True)
        sidebar.set_hexpand(False)
        sidebar_wrap.append(sidebar)
        self.sidebar_revealer = Gtk.Revealer(
            transition_type=Gtk.RevealerTransitionType.FADE_SLIDE_LEFT,
            transition_duration=260,
        )
        self.sidebar_revealer.set_child(sidebar_wrap)
        self.sidebar_revealer.set_hexpand(False)
        self.sidebar_revealer.set_reveal_child(not bool(app.config.data.get("sidebar_collapsed", False)))
        split.append(self.sidebar_revealer)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)
        split.append(self.stack)
        content_canvas = Gtk.Overlay()
        self.backdrop = LiquidGlassBackdrop(
            bool(app.config.data["dark_mode"]),
            str(app.config.data.get("color_theme", "teal")),
        )
        content_canvas.set_child(self.backdrop)
        content_canvas.add_overlay(split)
        toolbar.set_content(content_canvas)

        self.dashboard = self._build_dashboard()
        self.breathing_page = self._build_breathing()
        self.training_page = self._build_training()
        self.habits_page = self._build_habits()
        self.achievements_page = self._build_achievements()
        self.analytics = self._build_analytics()
        self.settings_page = self._build_settings()
        self.health_page = self._build_health()
        self.stack.add_titled(self.dashboard, "today", self._t("Обзор"))
        self.stack.get_page(self.dashboard).set_icon_name("view-grid-symbolic")
        self.stack.add_titled(self.breathing_page, "breathing", self._t("Дыхание"))
        self.stack.get_page(self.breathing_page).set_icon_name("weather-windy-symbolic")
        self.stack.add_titled(self.training_page, "training", self._t("Тренировки"))
        self.stack.get_page(self.training_page).set_icon_name("applications-engineering-symbolic")
        self.stack.add_titled(self.habits_page, "habits", self._t("Привычки"))
        self.stack.get_page(self.habits_page).set_icon_name("object-select-symbolic")
        self.stack.add_titled(self.achievements_page, "achievements", self._t("Достижения"))
        self.stack.get_page(self.achievements_page).set_icon_name("emblem-default-symbolic")
        self.stack.add_titled(self.analytics, "analytics", self._t("Аналитика"))
        self.stack.get_page(self.analytics).set_icon_name("org.gnome.Settings-about-symbolic")
        self.stack.add_titled(self.settings_page, "settings", self._t("Настройки"))
        self.stack.get_page(self.settings_page).set_icon_name("preferences-system-symbolic")
        self.stack.add_titled(self.health_page, "health", self._t("Важно"))
        self.stack.get_page(self.health_page).set_icon_name("dialog-warning-symbolic")
        self.stack.connect("notify::visible-child-name", self._page_changed)
        # Swap a completely built tree in one operation. Attaching an empty stack
        # first lets GTK resize the window while longer translated labels arrive.
        self.set_content(toolbar)
        self._apply_sidebar_state(bool(app.config.data.get("sidebar_collapsed", False)))
        self.apply_theme_state(bool(app.config.data["dark_mode"]))
        self.refresh()

    def _apply_sidebar_state(self, collapsed: bool) -> None:
        self.sidebar_revealer.set_reveal_child(not collapsed)
        self.sidebar_open_button.set_visible(collapsed)

    def _hide_sidebar(self, _button: Gtk.Button | None = None) -> None:
        self.app.config.data["sidebar_collapsed"] = True
        self.app.config.save()
        self._apply_sidebar_state(True)

    def _show_sidebar(self, _button: Gtk.Button | None = None) -> None:
        self.app.config.data["sidebar_collapsed"] = False
        self.app.config.save()
        self._apply_sidebar_state(False)

    def reload_language(self, page: str = "settings") -> bool:
        """Rebuild the widget tree inside the same native window surface."""
        width = self.get_width()
        height = self.get_height()
        maximized = self.is_maximized()
        self.language = str(self.app.config.data.get("language", "en"))
        self.set_title("Zdorovo" if self.language == "en" else APP_NAME)
        self._build_window_content()
        if page in (
            "today",
            "breathing",
            "training",
            "habits",
            "achievements",
            "analytics",
            "settings",
            "health",
        ):
            self.stack.set_visible_child_name(page)
        self.refresh(rebuild_lists=True)
        if not maximized:
            self.set_default_size(width, height)
        return GLib.SOURCE_REMOVE

    def _t(self, russian: str) -> str:
        return localized_text(self.language, russian)

    def _translate_tree(self, widget: Gtk.Widget) -> None:
        if self.language == "en" and isinstance(widget, Gtk.Label):
            current = widget.get_text()
            translated = localized_text("en", current)
            if translated != current:
                widget.set_text(translated)
        child = widget.get_first_child()
        while child:
            self._translate_tree(child)
            child = child.get_next_sibling()

    def _page(self) -> tuple[Adw.BreakpointBin, Gtk.Box]:
        scroller = Gtk.ScrolledWindow(
            # Pages reflow at their breakpoints. Keeping the outer scroller
            # vertical-only prevents a rebuilt page from retaining a wider
            # natural size and sliding beyond the window edge.
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            css_classes=["glass-page"],
        )
        scroller.set_overlay_scrolling(True)
        responsive_page = Adw.BreakpointBin()
        responsive_page.set_size_request(480, 360)
        responsive_page.set_child(scroller)
        breakpoint = Adw.Breakpoint()
        # Keep useful two- and three-column groups intact while they still fit.
        # The previous 950sp threshold stacked pages much too early once the
        # navigation sidebar had taken its share of a normal desktop window.
        breakpoint.set_condition(Adw.BreakpointCondition.parse("max-width: 650sp"))
        responsive_page.add_breakpoint(breakpoint)
        self._building_page_breakpoint = breakpoint
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, css_classes=["page-content"])
        content.set_vexpand(True)
        content.set_margin_top(22)
        content.set_margin_bottom(18)
        content.set_margin_start(24)
        content.set_margin_end(24)
        breakpoint.add_setter(content, "margin-start", 16)
        breakpoint.add_setter(content, "margin-end", 16)
        page.append(content)
        page.append(cyberjabka_footer())
        scroller.set_child(page)
        return responsive_page, content

    def _stack_when_compact(self, box: Gtk.Box) -> Gtk.Box:
        """Stack a wide group when its page no longer has enough room."""
        self._building_page_breakpoint.add_setter(
            box,
            "orientation",
            Gtk.Orientation.VERTICAL,
        )
        return box

    @staticmethod
    def _responsive_flow(css_class: str, columns: int = 2, spacing: int = 10) -> Gtk.FlowBox:
        flow = Gtk.FlowBox(css_classes=[css_class, "responsive-flow"])
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_min_children_per_line(1)
        flow.set_max_children_per_line(columns)
        flow.set_column_spacing(spacing)
        flow.set_row_spacing(spacing)
        flow.set_homogeneous(True)
        return flow

    def _refresh_notification_center(self) -> None:
        if not hasattr(self, "notification_list"):
            return
        unread = self.app.db.unread_notifications()
        self.notification_badge.set_text(notification_badge_text(unread))
        self.notification_badge.set_visible(unread > 0)
        clear_box(self.notification_list)
        rows = self.app.db.notifications(20)
        if not rows:
            empty = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=5,
                css_classes=["notification-empty"],
            )
            empty.append(Gtk.Image.new_from_icon_name("notifications-disabled-symbolic"))
            empty.append(
                Gtk.Label(
                    label="No notifications yet" if self.language == "en" else "Пока нет уведомлений",
                    css_classes=["muted"],
                )
            )
            self.notification_list.append(empty)
            return
        icons = {
            "habit": "object-select-symbolic",
            "wellness": "user-available-symbolic",
            "breathing": "weather-windy-symbolic",
            "training": "applications-engineering-symbolic",
            "achievement": "emblem-default-symbolic",
            "info": "dialog-information-symbolic",
        }
        now = time.time()
        for row in rows:
            button = Gtk.Button(css_classes=["notification-row"])
            if not int(row["is_read"]):
                button.add_css_class("unread")
            box = Gtk.Box(spacing=9)
            box.append(
                symbolic_icon(
                    icons.get(str(row["kind"]), "dialog-information-symbolic"), 18, "notification-icon"
                )
            )
            copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
            copy.append(
                Gtk.Label(
                    label=str(row["title"]),
                    xalign=0,
                    wrap=True,
                    css_classes=["notification-title"],
                )
            )
            copy.append(
                Gtk.Label(
                    label=notification_body_for_display(str(row["kind"]), str(row["body"]), self.language),
                    xalign=0,
                    wrap=True,
                    max_width_chars=38,
                    css_classes=["muted", "caption"],
                )
            )
            age = max(0, int(now - float(row["created_at"])))
            if age < 60:
                age_text = "now" if self.language == "en" else "сейчас"
            elif age < 3600:
                age_text = f"{age // 60} min ago" if self.language == "en" else f"{age // 60} мин назад"
            elif age < 86400:
                age_text = f"{age // 3600} h ago" if self.language == "en" else f"{age // 3600} ч назад"
            else:
                age_text = datetime.fromtimestamp(float(row["created_at"])).strftime("%d.%m")
            copy.append(Gtk.Label(label=age_text, xalign=0, css_classes=["notification-time"]))
            box.append(copy)
            button.set_child(box)
            button.connect("clicked", self._open_notification_page, str(row["page"]))
            self.notification_list.append(button)

    def _notification_popover_changed(self, button: Gtk.MenuButton, _pspec: Any) -> None:
        if button.get_active():
            self._refresh_notification_center()

    def _mark_notifications_read(self, _button: Gtk.Button | None = None) -> None:
        self.app.db.mark_notifications_read()
        self._refresh_notification_center()

    def _open_notification_page(self, _button: Gtk.Button, page: str) -> None:
        self.app.db.mark_notifications_read()
        if page in (
            "today",
            "breathing",
            "training",
            "habits",
            "achievements",
            "analytics",
            "settings",
            "health",
        ):
            self.stack.set_visible_child_name(page)
        self.notification_button.popdown()
        self._refresh_notification_center()

    def _heading(self, title: str, subtitle: str) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.append(Gtk.Label(label=title, xalign=0, css_classes=["page-title"]))
        box.append(Gtk.Label(label=subtitle, xalign=0, wrap=True, css_classes=["muted"]))
        return box

    def _build_dashboard(self) -> Gtk.Widget:
        scroller, content = self._page()
        hero = Gtk.Box(spacing=26, css_classes=["hero-card"])
        hero_copy = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8, hexpand=True, valign=Gtk.Align.CENTER
        )
        hero_copy.append(Gtk.Label(label="БЕРЕЖНЫЙ РАБОЧИЙ РИТМ", xalign=0, css_classes=["hero-kicker"]))
        hero_copy.append(
            Gtk.Label(label="Работайте без перегруза", xalign=0, wrap=True, css_classes=["hero-title"])
        )
        hero_controls = Gtk.Box(spacing=12, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.hero_pause_button = Gtk.Button(
            icon_name="media-playback-pause-symbolic",
            css_classes=["hero-control-button"],
            tooltip_text="Pause timers" if self.language == "en" else "Приостановить таймеры",
        )
        self.hero_pause_button.set_size_request(44, 44)
        self.hero_pause_button.set_hexpand(False)
        self.hero_pause_button.set_vexpand(False)
        self.hero_pause_button.set_halign(Gtk.Align.CENTER)
        self.hero_pause_button.set_valign(Gtk.Align.CENTER)
        self.hero_pause_button.connect("clicked", self._toggle_manual_pause)
        hero_visual = Gtk.CenterBox(
            halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER, css_classes=["hero-orb"]
        )
        self.hero_value = Gtk.CenterBox(orientation=Gtk.Orientation.VERTICAL)
        hero_value_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.hero_number = Gtk.Label(label="20", css_classes=["hero-number"])
        self.hero_unit = Gtk.Label(label="min" if self.language == "en" else "мин", css_classes=["hero-unit"])
        hero_value_copy.append(self.hero_number)
        hero_value_copy.append(self.hero_unit)
        self.hero_value.set_center_widget(hero_value_copy)
        hero_visual.set_center_widget(self.hero_value)
        hero_controls.append(self.hero_pause_button)
        hero_controls.append(hero_visual)
        hero.append(hero_copy)
        hero.append(hero_controls)
        content.append(hero)
        self.manual_pause_banner = status_banner("Напоминания на паузе · экранное время продолжает считаться")
        set_status_banner_state(
            self.manual_pause_banner,
            bool(self.app.config.data["manual_pause"]),
        )
        content.append(self.manual_pause_banner)
        self.screen_share_banner = status_banner(
            "Идёт демонстрация экрана · напоминания отложены, экранное время считается"
        )
        set_status_banner_state(self.screen_share_banner, False)
        content.append(self.screen_share_banner)
        self.tracking_banner = status_banner(
            "Считается общее активное время · по приложениям — после следующего входа в GNOME"
        )
        set_status_banner_state(
            self.tracking_banner,
            not self.app.scheduler.extension_live(),
        )
        content.append(self.tracking_banner)
        # These compact values still fit at the supported minimum window width.
        # Keeping them horizontal avoids wasting a full row per value while the
        # larger dashboard sections can continue to reflow independently.
        cards = Gtk.Box(spacing=14, homogeneous=True)
        self.screen_value = Gtk.Label(css_classes=["metric-value"], xalign=0)
        self.breaks_value = Gtk.Label(css_classes=["metric-value"], xalign=0)
        self.next_value = Gtk.Label(css_classes=["metric-value", "accent-text"], xalign=0)
        cards.append(self._metric_card("Экран сегодня", self.screen_value, "активное время"))
        cards.append(self._metric_card("Паузы", self.breaks_value, "выполнено сегодня"))
        cards.append(self._metric_card("Следующая пауза", self.next_value, "по активному времени"))
        content.append(cards)

        health_grid = self._stack_when_compact(
            Gtk.Box(spacing=12, hexpand=True, css_classes=["dashboard-health-grid"])
        )
        wellness = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=9, css_classes=["card", "wellness-card"]
        )
        wellness.set_valign(Gtk.Align.FILL)
        wellness.set_hexpand(True)
        self.wellness_card = wellness
        wellness.set_visible(bool(self.app.config.data.get("wellness_checkin_enabled", True)))
        wellness.append(Gtk.Label(label="Самочувствие сейчас", xalign=0, css_classes=["section-title"]))
        wellness.append(
            Gtk.Label(
                label="Отметьте выраженность от 0 до 10. Это дневник, а не диагноз.",
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        self.wellness_scales: dict[str, Gtk.Scale] = {}
        self.wellness_values: dict[str, Gtk.Label] = {}
        latest = self.app.db.latest_wellness()
        for key, label_text in (
            ("headache", "Головная боль"),
            ("eyes", "Усталость глаз"),
            ("neck", "Шея и плечи"),
            ("back", "Поясница"),
        ):
            row = Gtk.Box(spacing=9, css_classes=["wellness-row"])
            row.append(Gtk.Label(label=label_text, xalign=0, width_chars=15, css_classes=["wellness-label"]))
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 10, 1)
            scale.set_draw_value(False)
            scale.set_hexpand(True)
            scale.set_value(float(latest[key]) if latest else 0)
            value = Gtk.Label(
                label=str(int(scale.get_value())), width_chars=2, css_classes=["wellness-score"]
            )
            scale.connect(
                "value-changed", lambda widget, output=value: output.set_text(str(int(widget.get_value())))
            )
            scroll_guard = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
            scroll_guard.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            scroll_guard.connect("scroll", self._wellness_scale_scrolled)
            scale.add_controller(scroll_guard)
            row.append(scale)
            row.append(value)
            wellness.append(row)
            self.wellness_scales[key] = scale
            self.wellness_values[key] = value
        wellness_actions = Gtk.Box(spacing=9)
        self.wellness_status = Gtk.Label(
            label=self._wellness_saved_text(float(latest["created_at"]))
            if latest
            else self._t("Пока нет отметок"),
            xalign=0,
            hexpand=True,
            css_classes=["muted", "caption"],
        )
        wellness_actions.append(self.wellness_status)
        wellness_save = Gtk.Button(label="Сохранить самочувствие", css_classes=["health-primary"])
        wellness_save.connect("clicked", self._save_wellness)
        wellness_actions.append(wellness_save)
        wellness.append(Gtk.Box(vexpand=True))
        wellness.append(wellness_actions)
        health_grid.append(wellness)

        quick = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9, css_classes=["card", "quick-card"])
        quick.set_valign(Gtk.Align.FILL)
        quick.set_hexpand(True)
        quick.set_size_request(250, -1)
        self._building_page_breakpoint.add_setter(quick, "hexpand", True)
        quick.append(Gtk.Label(label="Быстрый старт", xalign=0, css_classes=["section-title"]))
        quick.append(
            Gtk.Label(
                label="Не ждите таймера, если пауза нужна уже сейчас.",
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        quick_buttons = Gtk.Box(spacing=8, homogeneous=True)
        for kind, title in (("eyes", "Глаза"), ("general", "Размяться"), ("neck", "Шея")):
            button = Gtk.Button(css_classes=["quick-action"])
            button_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, halign=Gtk.Align.CENTER)
            button_box.append(activity_icon(kind, 19))
            button_box.append(
                Gtk.Label(
                    label=title,
                    wrap=True,
                    max_width_chars=9,
                    justify=Gtk.Justification.CENTER,
                )
            )
            button.set_child(button_box)
            button.connect("clicked", lambda _button, selected=kind: self.app.scheduler.trigger(selected))
            quick_buttons.append(button)
        quick.append(quick_buttons)
        quick_context = Gtk.CenterBox(
            orientation=Gtk.Orientation.VERTICAL,
            css_classes=["quick-context"],
        )
        quick_context_copy = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4,
            valign=Gtk.Align.CENTER,
        )
        quick_context_copy.append(
            Gtk.Label(label="БЛИЖАЙШЕЕ ПО ПЛАНУ", xalign=0, css_classes=["quick-context-kicker"])
        )
        self.quick_next_title = Gtk.Label(xalign=0, wrap=True, css_classes=["quick-context-title"])
        self.quick_next_due = Gtk.Label(xalign=0, wrap=True, css_classes=["muted", "caption"])
        quick_context_copy.append(self.quick_next_title)
        quick_context_copy.append(self.quick_next_due)
        quick_context.set_center_widget(quick_context_copy)
        quick.append(quick_context)
        health_grid.append(quick)
        content.append(health_grid)

        content.append(Gtk.Label(label="Ближайшие напоминания", xalign=0, css_classes=["section-title"]))
        self.reminder_grid = self._responsive_flow("reminder-flow", spacing=12)
        self._building_page_breakpoint.add_setter(
            self.reminder_grid,
            "max-children-per-line",
            1,
        )
        self.reminder_due_labels: dict[str, Gtk.Label] = {}
        self.reminder_title_labels: dict[str, Gtk.Label] = {}
        content.append(self.reminder_grid)
        return scroller

    def _wellness_scale_scrolled(self, controller: Gtk.EventControllerScroll, _dx: float, dy: float) -> bool:
        """Keep wheel scrolling for the page without changing a wellbeing score."""
        widget = controller.get_widget()
        scroller = widget.get_ancestor(Gtk.ScrolledWindow) if widget else None
        if scroller:
            adjustment = scroller.get_vadjustment()
            target = adjustment.get_value() + dy * 52.0
            maximum = max(adjustment.get_lower(), adjustment.get_upper() - adjustment.get_page_size())
            adjustment.set_value(max(adjustment.get_lower(), min(maximum, target)))
        return True

    def _metric_card(self, title: str, value: Gtk.Label, hint: str) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["card", "metric-card"])
        box.append(Gtk.Label(label=title, xalign=0, css_classes=["metric-label"]))
        box.append(value)
        box.append(Gtk.Label(label=hint, xalign=0, css_classes=["muted", "caption"]))
        return box

    def _build_breathing(self) -> Gtk.Widget:
        scroller, content = self._page()
        content.append(
            self._heading(
                "Дыхательная пауза",
                "Мягкий визуальный ритм без форсированных вдохов и обязательных задержек.",
            )
        )
        guide = self._stack_when_compact(Gtk.Box(spacing=28, css_classes=["breathing-guide-card"]))
        self.breathing_orb = BreathingOrb(str(self.app.config.data.get("color_theme", "teal")))
        visual = Gtk.Overlay(css_classes=["breathing-visual"])
        visual.set_child(self.breathing_orb)
        orb_copy = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=1,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
            css_classes=["breathing-orb-copy"],
        )
        self.breathing_phase = Gtk.Label(label="Готовы начать", css_classes=["breathing-phase"])
        self.breathing_countdown = Gtk.Label(label="05:00", css_classes=["breathing-countdown"])
        orb_copy.append(self.breathing_phase)
        orb_copy.append(self.breathing_countdown)
        visual.add_overlay(orb_copy)
        guide.append(visual)
        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, hexpand=True)
        copy.append(
            Gtk.Label(
                label="GUIDED BREATHING" if self.language == "en" else "ДЫХАТЕЛЬНЫЙ РИТМ",
                xalign=0,
                css_classes=["breathing-kicker"],
            )
        )
        self.breathing_program_title = Gtk.Label(xalign=0, css_classes=["breathing-program-title"])
        self.breathing_program_description = Gtk.Label(
            xalign=0, wrap=True, css_classes=["breathing-program-copy"]
        )
        copy.append(self.breathing_program_title)
        copy.append(self.breathing_program_description)
        rhythm = Gtk.Box(spacing=8, css_classes=["breathing-rhythm"])
        inhale_chip = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=1, css_classes=["breathing-rhythm-chip"]
        )
        inhale_chip.append(
            Gtk.Label(
                label="INHALE" if self.language == "en" else "ВДОХ",
                css_classes=["breathing-rhythm-label"],
            )
        )
        self.breathing_inhale_value = Gtk.Label(css_classes=["breathing-rhythm-value"])
        inhale_chip.append(self.breathing_inhale_value)
        exhale_chip = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=1, css_classes=["breathing-rhythm-chip"]
        )
        exhale_chip.append(
            Gtk.Label(
                label="EXHALE" if self.language == "en" else "ВЫДОХ",
                css_classes=["breathing-rhythm-label"],
            )
        )
        self.breathing_exhale_value = Gtk.Label(css_classes=["breathing-rhythm-value"])
        exhale_chip.append(self.breathing_exhale_value)
        rhythm.append(inhale_chip)
        rhythm.append(exhale_chip)
        copy.append(rhythm)
        self.breathing_instruction = Gtk.Label(
            label="Сядьте удобно, расслабьте плечи и дышите без усилия.",
            xalign=0,
            wrap=True,
            css_classes=["breathing-instruction"],
        )
        copy.append(self.breathing_instruction)
        preset_box = self._stack_when_compact(
            Gtk.Box(spacing=10, homogeneous=True, css_classes=["breathing-presets"])
        )
        self.breathing_preset_buttons: dict[str, Gtk.Button] = {}
        for key, preset in BREATHING_PRESETS.items():
            button = Gtk.Button(css_classes=["breathing-preset"])
            button_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            button_copy.append(
                Gtk.Label(
                    label=self._t(str(preset["title"])),
                    xalign=0,
                    css_classes=["breathing-preset-title"],
                )
            )
            button_copy.append(
                Gtk.Label(
                    label=self._t(str(preset["description"])),
                    xalign=0,
                    wrap=True,
                    max_width_chars=28,
                    css_classes=["breathing-preset-description"],
                )
            )
            stats = Gtk.Grid(
                column_spacing=6, column_homogeneous=True, css_classes=["breathing-preset-stats"]
            )
            for index, (label_text, value_text) in enumerate(
                (
                    (
                        "Duration" if self.language == "en" else "Время",
                        format_duration(float(preset["duration"]), self.language),
                    ),
                    (
                        "Inhale" if self.language == "en" else "Вдох",
                        f"{preset['inhale']} {'sec' if self.language == 'en' else 'сек'}",
                    ),
                    (
                        "Exhale" if self.language == "en" else "Выдох",
                        f"{preset['exhale']} {'sec' if self.language == 'en' else 'сек'}",
                    ),
                )
            ):
                stat = Gtk.Box(
                    orientation=Gtk.Orientation.VERTICAL, spacing=1, css_classes=["breathing-preset-stat"]
                )
                stat.append(
                    Gtk.Label(label=label_text, xalign=0, css_classes=["breathing-preset-stat-label"])
                )
                stat.append(
                    Gtk.Label(label=value_text, xalign=0, css_classes=["breathing-preset-stat-value"])
                )
                stats.attach(stat, index, 0, 1, 1)
            button_copy.append(stats)
            button.set_child(button_copy)
            button.connect("clicked", self._select_breathing_preset, key)
            preset_box.append(button)
            self.breathing_preset_buttons[key] = button
        actions = Gtk.Box(spacing=8, css_classes=["breathing-actions"])
        self.breathing_start_button = Gtk.Button(
            css_classes=["health-primary", "breathing-primary"], hexpand=True
        )
        self.breathing_start_button.connect("clicked", self._toggle_breathing_session)
        self.breathing_stop_button = Gtk.Button(label=self._t("Сбросить"), css_classes=["data-button"])
        self.breathing_stop_button.set_size_request(120, -1)
        self.breathing_stop_button.connect("clicked", self._stop_breathing_session)
        actions.append(self.breathing_start_button)
        actions.append(self.breathing_stop_button)
        copy.append(actions)
        guide.append(copy)
        content.append(guide)

        preset_card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=9,
            css_classes=["card", "breathing-preset-card"],
        )
        preset_head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        preset_head.append(Gtk.Label(label="Выберите ритм", xalign=0, css_classes=["section-title"]))
        preset_head.append(
            Gtk.Label(
                label="Все режимы идут без обязательной задержки дыхания.",
                xalign=0,
                css_classes=["muted", "caption"],
            )
        )
        preset_card.append(preset_head)
        preset_card.append(preset_box)
        content.append(preset_card)

        metrics = self._stack_when_compact(
            Gtk.Box(
                spacing=10,
                homogeneous=True,
                css_classes=["breathing-metrics"],
            )
        )
        self.breathing_today_value = Gtk.Label(xalign=0, css_classes=["metric-value"])
        self.breathing_week_value = Gtk.Label(xalign=0, css_classes=["metric-value"])
        self.breathing_minutes_value = Gtk.Label(xalign=0, css_classes=["metric-value"])
        for title, value, hint in (
            ("Сегодня", self.breathing_today_value, "завершённых сессий"),
            ("За 7 дней", self.breathing_week_value, "завершённых сессий"),
            ("Практика", self.breathing_minutes_value, "за последние 7 дней"),
        ):
            metrics.append(self._metric_card(title, value, hint))
        content.append(metrics)

        schedule = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            css_classes=["card", "breathing-schedule-card"],
        )
        schedule_head = Gtk.Box(spacing=12)
        schedule_head.append(activity_icon("breathing", 24))
        schedule_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        schedule_copy.append(
            Gtk.Label(label="Автоматические дыхательные паузы", xalign=0, css_classes=["settings-title"])
        )
        schedule_copy.append(
            Gtk.Label(
                label="Использует общий таймер активной работы и не показывается во время демонстрации экрана.",
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        schedule_head.append(schedule_copy)
        breathing_options = self.app.config.reminder("breathing")
        schedule_switch = Gtk.Switch(
            active=bool(breathing_options.get("enabled", False)), valign=Gtk.Align.CENTER
        )
        schedule_switch.connect("notify::active", self._breathing_reminder_changed)
        schedule_head.append(schedule_switch)
        schedule.append(schedule_head)
        interval_row = Gtk.Box(spacing=10, css_classes=["breathing-interval-row"])
        interval_row.append(
            Gtk.Label(
                label="Frequency" if self.language == "en" else "Частота",
                xalign=0,
                hexpand=True,
                css_classes=["muted", "caption"],
            )
        )
        interval_control, _ = self._make_stepper(
            int(breathing_options.get("interval_minutes", 120)),
            30,
            480,
            30,
            lambda value: self._set_reminder_frequency("breathing", value),
            lambda value: f"every {value} min" if self.language == "en" else f"каждые {value} мин",
        )
        interval_control.set_size_request(220, -1)
        interval_row.append(interval_control)
        schedule.append(interval_row)
        content.append(schedule)
        safety = Gtk.Label(
            label=(
                "Дышите настолько неглубоко и медленно, насколько комфортно. Если появляется головокружение, покалывание, нехватка воздуха или другие неприятные ощущения — вернитесь к обычному дыханию. Индивидуальные ограничения лучше обсудить с врачом."
            ),
            xalign=0,
            wrap=True,
            css_classes=["wellness-insight", "caption"],
        )
        content.append(safety)
        self._update_breathing_ui()
        return scroller

    def _select_breathing_preset(self, _button: Gtk.Button, key: str) -> None:
        if self.breathing_running or key not in BREATHING_PRESETS:
            return
        self.breathing_preset = key
        self.breathing_elapsed = 0.0
        self._update_breathing_ui()

    def _toggle_breathing_session(self, _button: Gtk.Button) -> None:
        preset = BREATHING_PRESETS[self.breathing_preset]
        if self.breathing_elapsed >= float(preset["duration"]):
            self.breathing_elapsed = 0.0
        self.breathing_running = not self.breathing_running
        self.breathing_last_tick = time.monotonic()
        if self.breathing_running and self.breathing_timer_source is None:
            self.breathing_timer_source = GLib.timeout_add(100, self._breathing_tick)
        self._update_breathing_ui()

    def _stop_breathing_session(self, _button: Gtk.Button | None = None) -> None:
        self.breathing_running = False
        self.breathing_elapsed = 0.0
        if self.breathing_timer_source is not None:
            GLib.source_remove(self.breathing_timer_source)
            self.breathing_timer_source = None
        self._update_breathing_ui()

    def _breathing_tick(self) -> bool:
        if not self.breathing_running:
            self.breathing_timer_source = None
            return GLib.SOURCE_REMOVE
        now = time.monotonic()
        self.breathing_elapsed += min(1.0, max(0.0, now - self.breathing_last_tick))
        self.breathing_last_tick = now
        duration = float(BREATHING_PRESETS[self.breathing_preset]["duration"])
        if self.breathing_elapsed >= duration:
            self.breathing_elapsed = duration
            self.breathing_running = False
            self.breathing_timer_source = None
            self.app.db.log_reminder("breathing", "done", duration_seconds=duration)
            habit = next(
                (
                    item
                    for item in self.app.config.data.get("habits", [])
                    if item.get("id") == "breathing-pause" and item.get("enabled")
                ),
                None,
            )
            if habit and self.app.db.habit_count("breathing-pause") < int(habit.get("target", 1)):
                self.app.db.log_habit("breathing-pause")
            activity = self.app.scheduler.read_activity()
            self.app.push_app_notification(
                "breathing",
                "Breathing session complete" if self.language == "en" else "Дыхательная сессия завершена",
                (
                    f"Completed {format_duration(duration, self.language)} of gentle paced breathing."
                    if self.language == "en"
                    else f"Завершено {format_duration(duration, self.language)} мягкого дыхания в заданном ритме."
                ),
                "breathing",
                button="Open" if self.language == "en" else "Открыть",
                system=not (
                    bool(self.app.config.data.get("pause_on_screen_share", True)) and activity.screen_sharing
                ),
            )
            play_guidance_sound(self.app.config.data, "done")
            self._update_breathing_ui()
            self.refresh(rebuild_lists=False)
            return GLib.SOURCE_REMOVE
        self._update_breathing_ui()
        return GLib.SOURCE_CONTINUE

    def _update_breathing_ui(self) -> None:
        if not hasattr(self, "breathing_orb"):
            return
        preset = BREATHING_PRESETS[self.breathing_preset]
        duration = float(preset["duration"])
        self.breathing_program_title.set_text(self._t(str(preset["title"])))
        self.breathing_program_description.set_text(self._t(str(preset["description"])))
        self.breathing_inhale_value.set_text(
            f"{preset['inhale']} {'sec' if self.language == 'en' else 'сек'}"
        )
        self.breathing_exhale_value.set_text(
            f"{preset['exhale']} {'sec' if self.language == 'en' else 'сек'}"
        )
        phase, phase_progress = breathing_phase(preset, self.breathing_elapsed)
        if phase == "ready":
            phase_text = "Ready" if self.language == "en" else "Готовы начать"
            instruction = (
                "Sit comfortably, relax your shoulders and breathe without effort."
                if self.language == "en"
                else "Сядьте удобно, расслабьте плечи и дышите без усилия."
            )
        elif phase == "inhale":
            phase_text = "Inhale gently" if self.language == "en" else "Мягкий вдох"
            instruction = (
                "Let the abdomen expand only as far as comfortable."
                if self.language == "en"
                else "Позвольте животу расшириться только в комфортной амплитуде."
            )
        else:
            phase_text = "Exhale gently" if self.language == "en" else "Спокойный выдох"
            instruction = (
                "Release the air smoothly; do not push it out."
                if self.language == "en"
                else "Отпускайте воздух плавно, не выталкивая его силой."
            )
        remaining = max(0, math.ceil(duration - self.breathing_elapsed))
        self.breathing_phase.set_text(phase_text)
        self.breathing_countdown.set_text(f"{remaining // 60:02d}:{remaining % 60:02d}")
        self.breathing_instruction.set_text(instruction)
        self.breathing_orb.set_state(phase, phase_progress, self.breathing_elapsed / duration)
        self.breathing_start_button.set_label(
            ("Pause" if self.language == "en" else "Пауза")
            if self.breathing_running
            else ("Continue" if self.breathing_elapsed > 0 else "Start")
            if self.language == "en"
            else ("Продолжить" if self.breathing_elapsed > 0 else "Начать")
        )
        self.breathing_stop_button.set_sensitive(self.breathing_elapsed > 0)
        for key, button in self.breathing_preset_buttons.items():
            if key == self.breathing_preset:
                button.add_css_class("selected")
            else:
                button.remove_css_class("selected")
            button.set_sensitive(not self.breathing_running)

    def _breathing_reminder_changed(self, switch: Gtk.Switch, _pspec: Any) -> None:
        self.app.config.reminder("breathing")["enabled"] = switch.get_active()
        self.app.config.save()
        self.refresh(rebuild_lists=False)

    def _build_training(self) -> Gtk.Widget:
        page, content = self._page()
        self.training_scroller = page.get_child()
        heading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.training_page_title = Gtk.Label(xalign=0, css_classes=["page-title"])
        self.training_page_subtitle = Gtk.Label(
            xalign=0,
            wrap=True,
            css_classes=["muted"],
        )
        heading.append(self.training_page_title)
        heading.append(self.training_page_subtitle)
        content.append(heading)
        self.training_body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        content.append(self.training_body)
        self._rebuild_training()
        return page

    def _training_course_visual(
        self,
        course: dict[str, Any],
        active: bool = False,
        days_per_week: int | None = None,
        weekdays: Any = None,
    ) -> Gtk.Widget:
        visual = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=9,
            css_classes=[
                "training-course-visual",
                "training-active-visual" if active else "training-catalog-visual",
            ],
        )
        photo_frame: Gtk.Overlay | None = None
        image_path = ASSET_ROOT / str(course.get("image", ""))
        if image_path.exists():
            photo_height = 142 if active else 112
            photo_width = 190 if active else 150
            photo_frame = Gtk.Overlay(
                css_classes=["training-course-photo-frame"],
            )
            photo_frame.set_size_request(photo_width, photo_height)
            photo_frame.set_hexpand(False)
            photo_space = Gtk.Box()
            photo_space.set_size_request(photo_width, photo_height)
            photo_frame.set_child(photo_space)
            picture = Gtk.Picture(
                css_classes=[
                    "training-course-photo",
                    "training-active-photo" if active else "training-catalog-photo",
                ]
            )
            picture.set_filename(str(image_path))
            picture.set_content_fit(Gtk.ContentFit.CONTAIN)
            picture.set_can_shrink(True)
            picture.set_hexpand(True)
            picture.set_vexpand(True)
            picture.set_halign(Gtk.Align.FILL)
            picture.set_valign(Gtk.Align.FILL)
            photo_frame.add_overlay(picture)
            photo_frame.set_clip_overlay(picture, True)
        head = Gtk.Box(spacing=11, hexpand=True, valign=Gtk.Align.CENTER)
        head.append(activity_icon(str(course["icon"]), 29, "training-visual-icon"))
        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        copy.append(
            Gtk.Label(
                label=(
                    "WEEKLY RHYTHM"
                    if active and self.language == "en"
                    else "РИТМ НЕДЕЛИ"
                    if active
                    else "YOUR WEEK"
                    if self.language == "en"
                    else "ВАША НЕДЕЛЯ"
                ),
                xalign=0,
                css_classes=["training-visual-kicker"],
            )
        )
        copy.append(
            Gtk.Label(
                label=(
                    "Strength, lighter work and rest"
                    if active and self.language == "en"
                    else "Силовая работа, лёгкие дни и отдых"
                    if active
                    else "Training and recovery on your schedule"
                    if self.language == "en"
                    else "Нагрузка и восстановление по вашему расписанию"
                ),
                xalign=0,
                wrap=True,
                css_classes=["training-visual-title"],
            )
        )
        head.append(copy)
        media_row = Gtk.Box(spacing=12, css_classes=["training-course-media"])
        if photo_frame is not None:
            media_row.append(photo_frame)
        media_row.append(head)
        visual.append(media_row)

        strip = Gtk.Box(spacing=5, homogeneous=True, css_classes=["training-plan-strip"])
        chosen_weekdays = normalize_weekdays(
            weekdays if weekdays is not None else self.training_weekdays_choice,
            int(days_per_week or self.training_days_choice),
        )
        pattern = weekly_pattern(len(chosen_weekdays), weekdays=chosen_weekdays)
        weekday_labels = (
            ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
            if self.language == "en"
            else ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
        )
        for weekday, (kind, _session) in enumerate(pattern):
            visual_kind = "lighter" if kind in ("recovery", "mobility") else kind
            slot = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=4,
                css_classes=["training-plan-slot", f"training-plan-{visual_kind}"],
            )
            slot.append(
                Gtk.Label(
                    label=weekday_labels[weekday],
                    css_classes=["training-plan-day"],
                )
            )
            slot.append(Gtk.Box(css_classes=["training-plan-bar"]))
            strip.append(slot)
        visual.append(strip)
        if active:
            visual.append(
                Gtk.Label(
                    label=(
                        f"Selected: {self._weekday_names(chosen_weekdays, short=False)}"
                        if self.language == "en"
                        else f"Выбрано: {self._weekday_names(chosen_weekdays, short=False)}"
                    ),
                    xalign=0,
                    wrap=True,
                    css_classes=["training-active-weekdays", "caption"],
                )
            )
        return visual

    @staticmethod
    def _enrollment_weekdays(enrollment: sqlite3.Row) -> tuple[int, ...]:
        try:
            saved = json.loads(str(enrollment["weekdays"]))
        except (IndexError, KeyError, TypeError, ValueError):
            saved = None
        return normalize_weekdays(saved, int(enrollment["days_per_week"]))

    def _weekday_names(self, weekdays: Any, short: bool = True) -> str:
        names = (
            ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
            if self.language == "en" and short
            else ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
            if self.language == "en"
            else ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
            if short
            else ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
        )
        return ", ".join(names[index] for index in normalize_weekdays(weekdays))

    def _training_safety_card(self) -> Gtk.Widget:
        card = Gtk.Box(spacing=12, css_classes=["training-safety-card"])
        card.append(symbolic_icon("dialog-information-symbolic", 22, "training-safety-icon"))
        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        copy.append(
            Gtk.Label(
                label="Before you start" if self.language == "en" else "Перед началом",
                xalign=0,
                css_classes=["card-title"],
            )
        )
        copy.append(
            Gtk.Label(
                label=(
                    "These are general low-to-moderate-load routines, not treatment. Ask a clinician how to adapt exercise if symptoms recur. Stop for pain, numbness, weakness, dizziness or loss of coordination."
                    if self.language == "en"
                    else "Это общие комплексы с невысокой или умеренной нагрузкой, а не лечение. При повторяющихся симптомах обсудите адаптацию нагрузки с врачом. Остановитесь при боли, онемении, слабости, головокружении или нарушении координации."
                ),
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        card.append(copy)
        return card

    def _show_active_training(self, _button: Gtk.Button | None = None) -> None:
        if self.app.db.active_training() is None:
            return
        self._rebuild_active_training_at_top()

    def _scroll_training_to_top(self) -> bool:
        if hasattr(self, "training_scroller"):
            adjustment = self.training_scroller.get_vadjustment()
            adjustment.set_value(adjustment.get_lower())
        return GLib.SOURCE_REMOVE

    def _finish_opening_active_training(self) -> bool:
        if self.app.db.active_training() is None:
            return GLib.SOURCE_REMOVE
        if self.stack.get_visible_child_name() != "training":
            self.stack.set_visible_child_name("training")
        # Gtk.StackSidebar may emit its page-change notification after a
        # confirmation dialog responds. Re-assert the active view once that
        # event has settled so Reset progress cannot leave the catalogue open.
        if self.training_view != "active":
            self.training_view = "active"
            self._rebuild_training()
        self._scroll_training_to_top()
        return GLib.SOURCE_REMOVE

    def _rebuild_active_training_at_top(self) -> None:
        if self.stack.get_visible_child_name() != "training":
            self.stack.set_visible_child_name("training")
        self.training_view = "active"
        self._rebuild_training()
        GLib.idle_add(self._finish_opening_active_training)

    def _show_training_catalog(self, _button: Gtk.Button | None = None) -> None:
        active = self.app.db.active_training()
        if active is not None:
            self.training_course_choice = str(active["course_id"])
            saved_answers = {
                "full_body": ("balanced", "steady"),
                "upper_body": ("upper", "steady"),
                "legs": ("lower", "gentle"),
                "lower_body": ("lower", "strength"),
                "balance": ("mobility", "gentle"),
            }
            self.training_goal_choice, self.training_style_choice = saved_answers.get(
                self.training_course_choice,
                ("balanced", "steady"),
            )
        elif self.training_course_choice not in COURSES:
            self.training_course_choice = next(iter(COURSES))
        self.training_setup_step = 0
        self.training_view = "setup"
        self._rebuild_training()
        GLib.idle_add(self._scroll_training_to_top)

    def _rebuild_training(self) -> None:
        if not hasattr(self, "training_body"):
            return
        if hasattr(self, "training_page"):
            training_stack_page = self.stack.get_page(self.training_page)
            if training_stack_page is not None:
                training_stack_page.set_title(self._t("Тренировки"))
        clear_box(self.training_body)
        enrollment = self.app.db.active_training()
        if enrollment is None and self.training_view != "setup":
            self.training_setup_step = 0
            self.training_view = "setup"
        if enrollment and self.training_view != "setup":
            self.training_page_title.set_text(
                "Today’s course" if self.language == "en" else "Тренировка на сегодня"
            )
            self.training_page_subtitle.set_text(
                "One planned course day at a time, with recovery built into the schedule."
                if self.language == "en"
                else "Один запланированный день курса за раз; восстановление уже встроено в расписание."
            )
            self._render_active_training(enrollment)
        else:
            self.training_page_title.set_text(
                "Find your training plan" if self.language == "en" else "Подберите курс тренировок"
            )
            self.training_page_subtitle.set_text(
                "Answer a few short questions and get one clear plan for your week."
                if self.language == "en"
                else "Ответьте на несколько коротких вопросов и получите один понятный план на неделю."
            )
            self._render_training_catalog()

    def _training_setup_progress(self) -> Gtk.Widget:
        titles = (
            ("Goal", "Approach", "Schedule", "Level", "Length", "Plan")
            if self.language == "en"
            else ("Цель", "Подход", "Расписание", "Уровень", "Срок", "План")
        )
        progress = Gtk.Box(
            spacing=6,
            homogeneous=True,
            css_classes=["training-setup-progress"],
        )
        for index, title in enumerate(titles):
            item = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=4,
                css_classes=["training-setup-progress-item"],
            )
            if index < self.training_setup_step:
                item.add_css_class("complete")
            elif index == self.training_setup_step:
                item.add_css_class("current")
            item.append(
                Gtk.Label(
                    label=str(index + 1),
                    css_classes=["training-setup-progress-number"],
                )
            )
            item.append(
                Gtk.Label(
                    label=title,
                    wrap=True,
                    justify=Gtk.Justification.CENTER,
                    css_classes=["training-setup-progress-label"],
                )
            )
            progress.append(item)
        return progress

    def _recommended_training_course(self) -> str:
        if self.training_goal_choice == "upper":
            return "upper_body"
        if self.training_goal_choice == "mobility":
            return "balance"
        if self.training_goal_choice == "lower":
            return "lower_body" if self.training_style_choice == "strength" else "legs"
        return "full_body"

    def _training_goal_selected(self, button: Gtk.ToggleButton, goal: str) -> None:
        if button.get_active():
            self.training_goal_choice = goal
            self.training_course_choice = self._recommended_training_course()

    def _training_style_selected(self, button: Gtk.ToggleButton, style: str) -> None:
        if button.get_active():
            self.training_style_choice = style
            self.training_course_choice = self._recommended_training_course()

    def _training_answer_options(
        self,
        options: tuple[tuple[str, str, str], ...],
        selected: str,
        callback: Callable[[Gtk.ToggleButton, str], None],
    ) -> Gtk.Widget:
        choices = self._responsive_flow("training-answer-options", columns=2, spacing=9)
        first: Gtk.ToggleButton | None = None
        for value, title, description in options:
            button = Gtk.ToggleButton(css_classes=["training-answer-button"])
            if first is None:
                first = button
            else:
                button.set_group(first)
            copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            copy.append(
                Gtk.Label(
                    label=title,
                    xalign=0,
                    wrap=True,
                    css_classes=["card-title"],
                )
            )
            copy.append(
                Gtk.Label(
                    label=description,
                    xalign=0,
                    wrap=True,
                    css_classes=["muted", "caption"],
                )
            )
            button.set_child(copy)
            button.set_active(value == selected)
            button.connect("toggled", callback, value)
            choices.append(button)
        return choices

    def _training_recommendation_card(self) -> Gtk.Widget:
        self.training_course_choice = self._recommended_training_course()
        course = COURSES[self.training_course_choice]
        goal_reasons = (
            {
                "balanced": "You asked for balanced work across the whole body.",
                "upper": "You want more attention on the arms, shoulders and upper back.",
                "lower": "You want stronger legs and steadier everyday movement.",
                "mobility": "You want more comfortable mobility and supported balance practice.",
            }
            if self.language == "en"
            else {
                "balanced": "Вы выбрали равномерную работу для всего тела.",
                "upper": "Вам важнее руки, плечи и верхняя часть спины.",
                "lower": "Вы хотите укрепить ноги и увереннее двигаться в быту.",
                "mobility": "Вам важнее комфортная подвижность и баланс рядом с опорой.",
            }
        )
        style_reasons = (
            {
                "gentle": "The plan starts gently and keeps extra recovery between demanding days.",
                "steady": "The workload rises gradually without chasing exhaustion.",
                "strength": "The plan uses more strength-focused variations and progressive volume.",
            }
            if self.language == "en"
            else {
                "gentle": "План начинается мягко и оставляет больше восстановления между нагрузками.",
                "steady": "Нагрузка растёт постепенно, без работы до изнеможения.",
                "strength": "В плане больше силовых вариантов и постепенно растущий объём.",
            }
        )
        card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            css_classes=["card", "training-recommendation-card"],
        )
        card.append(
            self._training_course_visual(
                course,
                days_per_week=self.training_days_choice,
                weekdays=self.training_weekdays_choice,
            )
        )
        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        copy.append(
            Gtk.Label(
                label=training_copy(course, "title", self.language),
                xalign=0,
                wrap=True,
                css_classes=["training-recommendation-title"],
            )
        )
        copy.append(
            Gtk.Label(
                label=training_copy(course, "description", self.language),
                xalign=0,
                wrap=True,
                css_classes=["training-recommendation-description"],
            )
        )
        copy.append(
            Gtk.Label(
                label=(
                    f"{goal_reasons[self.training_goal_choice]} "
                    f"{style_reasons[self.training_style_choice]}"
                ),
                xalign=0,
                wrap=True,
                css_classes=["training-recommendation-reason"],
            )
        )
        card.append(copy)
        facts = self._responsive_flow("training-recommendation-facts", columns=3, spacing=7)
        level = FITNESS_LEVELS[self.training_fitness_choice]
        fact_values = (
            (
                ("Length", f"{self.training_duration_choice} days"),
                ("Level", training_copy(level, "title", self.language)),
                ("Training days", self._weekday_names(self.training_weekdays_choice)),
            )
            if self.language == "en"
            else (
                ("Длительность", f"{self.training_duration_choice} дней"),
                ("Уровень", training_copy(level, "title", self.language)),
                ("Дни тренировок", self._weekday_names(self.training_weekdays_choice)),
            )
        )
        for label, value in fact_values:
            fact = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=3,
                css_classes=["training-recommendation-fact"],
            )
            fact.append(Gtk.Label(label=label, xalign=0, css_classes=["muted", "caption"]))
            fact.append(
                Gtk.Label(
                    label=value,
                    xalign=0,
                    wrap=True,
                    css_classes=["card-title"],
                )
            )
            facts.append(fact)
        card.append(facts)
        equipment = Gtk.Box(spacing=7, css_classes=["training-equipment"])
        equipment.append(Gtk.Image.new_from_icon_name("applications-engineering-symbolic"))
        equipment.append(
            Gtk.Label(
                label=training_copy(course, "equipment", self.language),
                xalign=0,
                wrap=True,
                css_classes=["caption"],
            )
        )
        card.append(equipment)
        return card

    def _set_training_setup_step(self, _button: Gtk.Button | None, step: int) -> None:
        self.training_setup_step = max(0, min(5, int(step)))
        self.training_course_choice = self._recommended_training_course()
        self.training_view = "setup"
        self._rebuild_training()
        GLib.idle_add(self._scroll_training_to_top)

    def _cancel_training_setup(self, _button: Gtk.Button) -> None:
        if self.app.db.active_training() is not None:
            self._rebuild_active_training_at_top()

    def _finish_training_setup(self, button: Gtk.Button) -> None:
        active = self.app.db.active_training()
        if active is not None and str(active["course_id"]) == self.training_course_choice:
            self._rebuild_active_training_at_top()
            return
        self._start_training_course(button, self.training_course_choice)

    def _training_setup_actions(self) -> Gtk.Widget:
        actions = Gtk.Box(spacing=8, css_classes=["training-setup-actions"])
        active = self.app.db.active_training()
        if self.training_setup_step > 0:
            back = Gtk.Button(
                label="Back" if self.language == "en" else "Назад",
                css_classes=["data-button"],
            )
            back.connect("clicked", self._set_training_setup_step, self.training_setup_step - 1)
            actions.append(back)
        elif active is not None:
            cancel = Gtk.Button(
                label="Keep current course" if self.language == "en" else "Оставить текущий курс",
                css_classes=["data-button"],
            )
            cancel.connect("clicked", self._cancel_training_setup)
            actions.append(cancel)
        spacer = Gtk.Box(hexpand=True)
        actions.append(spacer)
        if self.training_setup_step < 5:
            next_button = Gtk.Button(
                label="Continue" if self.language == "en" else "Продолжить",
                css_classes=["health-primary", "training-setup-primary"],
            )
            next_button.connect("clicked", self._set_training_setup_step, self.training_setup_step + 1)
        else:
            same_course = active is not None and str(active["course_id"]) == self.training_course_choice
            next_button = Gtk.Button(
                label=(
                    "Open current course"
                    if same_course and self.language == "en"
                    else "Открыть текущий курс"
                    if same_course
                    else "Switch course"
                    if active is not None and self.language == "en"
                    else "Сменить курс"
                    if active is not None
                    else "Start course"
                    if self.language == "en"
                    else "Начать курс"
                ),
                css_classes=["health-primary", "training-setup-primary"],
            )
            next_button.connect("clicked", self._finish_training_setup)
        actions.append(next_button)
        return actions

    def _render_training_catalog(self) -> None:
        step = self.training_setup_step
        step_titles = (
            (
                "What would you like to improve?",
                "What pace feels realistic?",
                "Which days fit your week?",
                "How prepared do you feel?",
                "Choose the course length",
                "Your recommended plan",
            )
            if self.language == "en"
            else (
                "Что хотите улучшить?",
                "Какой темп вам подходит?",
                "В какие дни удобно заниматься?",
                "Какой уровень нагрузки подходит?",
                "Выберите длительность курса",
                "Ваш рекомендованный план",
            )
        )
        step_copies = (
            (
                "Choose the result that matters most right now. The app will select the course itself.",
                "This answer changes the balance between strength work and recovery.",
                "Choose from two to five days. Recovery stays between harder sessions.",
                "The level changes exercise variations, volume and rest time.",
                "Pick a horizon that feels achievable. You can change plans later.",
                "Review why this plan fits your answers, then start today’s workout.",
            )
            if self.language == "en"
            else (
                "Выберите самый важный результат на сейчас. Сам курс приложение подберёт автоматически.",
                "Ответ изменит соотношение силовой работы и восстановления.",
                "Выберите от двух до пяти дней. Между нагрузками останется восстановление.",
                "Уровень меняет варианты упражнений, объём работы и время отдыха.",
                "Выберите посильный горизонт. Позже план можно будет сменить.",
                "Посмотрите, почему план подходит под ваши ответы, и начните сегодняшнюю тренировку.",
            )
        )
        setup_head = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=11,
            css_classes=["card", "training-setup-head"],
        )
        setup_head.append(self._training_setup_progress())
        question = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        question.append(
            Gtk.Label(
                label=step_titles[step],
                xalign=0,
                wrap=True,
                css_classes=["section-title", "training-setup-question"],
            )
        )
        question.append(
            Gtk.Label(
                label=step_copies[step],
                xalign=0,
                wrap=True,
                css_classes=["muted", "training-setup-copy"],
            )
        )
        setup_head.append(question)
        self.training_body.append(setup_head)

        goal_options = (
            (
                (
                    "balanced",
                    "Feel stronger overall",
                    "A balanced plan for the legs, upper body and core.",
                ),
                (
                    "upper",
                    "Strengthen my upper body",
                    "More attention to the arms, shoulders and upper back.",
                ),
                (
                    "lower",
                    "Build stronger legs",
                    "Squats, hip work and steadier everyday movement.",
                ),
                (
                    "mobility",
                    "Move more comfortably",
                    "Mobility and supported balance with a gentler load.",
                ),
            )
            if self.language == "en"
            else (
                (
                    "balanced",
                    "Стать сильнее в целом",
                    "Равномерный план для ног, верха тела и мышц корпуса.",
                ),
                (
                    "upper",
                    "Укрепить верх тела",
                    "Больше внимания рукам, плечам и верхней части спины.",
                ),
                (
                    "lower",
                    "Укрепить ноги",
                    "Приседания, работа тазом и устойчивость в обычных движениях.",
                ),
                (
                    "mobility",
                    "Двигаться свободнее",
                    "Подвижность и баланс рядом с опорой при мягкой нагрузке.",
                ),
            )
        )
        goals = self._training_answer_options(
            goal_options,
            self.training_goal_choice,
            self._training_goal_selected,
        )
        goals.set_visible(step == 0)
        self.training_body.append(goals)

        style_options = (
            (
                (
                    "gentle",
                    "Start gently",
                    "Shorter work blocks, easier variations and more recovery.",
                ),
                (
                    "steady",
                    "Build gradually",
                    "A balanced pace with small increases from session to session.",
                ),
                (
                    "strength",
                    "Focus on strength",
                    "More demanding variations and progressive training volume.",
                ),
            )
            if self.language == "en"
            else (
                (
                    "gentle",
                    "Начать мягко",
                    "Короткие подходы, простые варианты и больше восстановления.",
                ),
                (
                    "steady",
                    "Наращивать постепенно",
                    "Ровный темп с небольшим усилением от тренировки к тренировке.",
                ),
                (
                    "strength",
                    "Сделать упор на силу",
                    "Более сложные варианты и постепенно растущий объём работы.",
                ),
            )
        )
        styles = self._training_answer_options(
            style_options,
            self.training_style_choice,
            self._training_style_selected,
        )
        styles.set_visible(step == 1)
        self.training_body.append(styles)

        duration_card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=13,
            css_classes=["card", "training-duration-card", "training-plan-builder"],
        )
        duration_card.set_visible(step in (2, 3, 4))
        duration_copy = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4,
            hexpand=True,
            valign=Gtk.Align.CENTER,
        )
        duration_copy.append(
            Gtk.Label(
                label="Choose a course length" if self.language == "en" else "Выберите длительность",
                xalign=0,
                css_classes=["section-title"],
            )
        )
        duration_copy.append(
            Gtk.Label(
                label=(
                    "Start with a week or keep the same recovery-friendly rhythm for a longer course."
                    if self.language == "en"
                    else "Начните с недели или сохраните тот же ритм с восстановлением на более длинном курсе."
                ),
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        duration_card.append(duration_copy)
        duration_copy.set_visible(step == 4)
        durations = Gtk.Box(
            spacing=7,
            homogeneous=True,
            valign=Gtk.Align.CENTER,
            css_classes=["training-duration-options"],
        )
        first_button: Gtk.ToggleButton | None = None
        for days in COURSE_DURATIONS:
            label = f"{days} days" if self.language == "en" else f"{days} дней"
            button = Gtk.ToggleButton(label=label, css_classes=["training-duration-button"])
            if first_button is None:
                first_button = button
            else:
                button.set_group(first_button)
            button.set_active(days == self.training_duration_choice)
            button.connect("toggled", self._training_duration_selected, days)
            durations.append(button)
        duration_card.append(durations)
        durations.set_visible(step == 4)

        weekly_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        weekly_copy.append(
            Gtk.Label(
                label="Choose training days" if self.language == "en" else "Выберите дни тренировок",
                xalign=0,
                css_classes=["card-title"],
            )
        )
        weekly_copy.append(
            Gtk.Label(
                label=(
                    "Choose two to five days. The remaining days stay free for recovery."
                    if self.language == "en"
                    else "Выберите от двух до пяти дней. Остальные дни останутся свободными для восстановления."
                ),
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        duration_card.append(weekly_copy)
        weekly_copy.set_visible(step == 2)
        weekly_options = Gtk.Box(
            spacing=7,
            homogeneous=True,
            css_classes=["training-duration-options", "training-weekly-options"],
        )
        short_names = (
            ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
            if self.language == "en"
            else ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
        )
        full_names = (
            ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
            if self.language == "en"
            else ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")
        )
        for weekday, label in enumerate(short_names):
            button = Gtk.ToggleButton(
                label=label,
                tooltip_text=full_names[weekday],
                css_classes=["training-duration-button", "training-weekday-button"],
            )
            button.set_active(weekday in self.training_weekdays_choice)
            button.connect("toggled", self._training_weekday_selected, weekday)
            weekly_options.append(button)
        duration_card.append(weekly_options)
        weekly_options.set_visible(step == 2)
        self.training_weekday_summary = Gtk.Label(
            label=(
                f"Selected: {self._weekday_names(self.training_weekdays_choice, short=False)}"
                if self.language == "en"
                else f"Выбрано: {self._weekday_names(self.training_weekdays_choice, short=False)}"
            ),
            xalign=0,
            wrap=True,
            css_classes=["training-weekday-summary", "muted", "caption"],
        )
        self.training_weekday_summary.set_visible(step == 2)
        duration_card.append(self.training_weekday_summary)

        level_title = Gtk.Label(
            label="Preparation level" if self.language == "en" else "Уровень подготовки",
            xalign=0,
            css_classes=["card-title"],
        )
        level_title.set_visible(step == 3)
        duration_card.append(level_title)
        levels = self._responsive_flow("training-level-options", columns=2, spacing=8)
        levels.set_min_children_per_line(2)
        first_level: Gtk.ToggleButton | None = None
        for level_id, level in FITNESS_LEVELS.items():
            button = Gtk.ToggleButton(css_classes=["training-level-button"])
            if first_level is None:
                first_level = button
            else:
                button.set_group(first_level)
            copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            copy.append(
                Gtk.Label(
                    label=training_copy(level, "title", self.language),
                    xalign=0,
                    css_classes=["card-title"],
                )
            )
            copy.append(
                Gtk.Label(
                    label=training_copy(level, "description", self.language),
                    xalign=0,
                    wrap=True,
                    max_width_chars=36,
                    css_classes=["muted", "caption"],
                )
            )
            button.set_child(copy)
            button.set_active(level_id == self.training_fitness_choice)
            button.connect("toggled", self._training_level_selected, level_id)
            levels.append(button)
        levels.set_visible(step == 3)
        duration_card.append(levels)
        chosen_level = FITNESS_LEVELS[self.training_fitness_choice]
        self.training_level_summary = Gtk.Label(
            label=(
                f"Selected: {training_copy(chosen_level, 'title', self.language)}. "
                f"{training_copy(chosen_level, 'description', self.language)}"
                if self.language == "en"
                else f"Выбрано: {training_copy(chosen_level, 'title', self.language)}. "
                f"{training_copy(chosen_level, 'description', self.language)}"
            ),
            xalign=0,
            wrap=True,
            css_classes=["training-level-summary", "muted", "caption"],
        )
        self.training_level_summary.set_visible(step == 3)
        duration_card.append(self.training_level_summary)
        reminder_separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        reminder_separator.set_visible(step == 4)
        duration_card.append(reminder_separator)
        reminder_settings = self._training_reminder_settings()
        reminder_settings.set_visible(step == 4)
        duration_card.append(reminder_settings)
        self.training_body.append(duration_card)

        recommendation = self._training_recommendation_card()
        recommendation.set_visible(step == 5)
        self.training_body.append(recommendation)
        safety = self._training_safety_card()
        safety.set_visible(step == 5)
        self.training_body.append(safety)

        self.training_body.append(self._training_setup_actions())

    def _training_calendar_card(self) -> Gtk.Widget:
        card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            css_classes=["card", "training-calendar-card"],
        )
        head = Gtk.Box(spacing=8)
        title = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        title.append(
            Gtk.Label(
                label="Training calendar" if self.language == "en" else "Календарь тренировок",
                xalign=0,
                css_classes=["section-title"],
            )
        )
        title.append(
            Gtk.Label(
                label=(
                    "Completed days remain here even after you switch or finish a course."
                    if self.language == "en"
                    else "Выполненные дни остаются здесь после смены или завершения курса."
                ),
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        head.append(title)
        previous = Gtk.Button(
            icon_name="go-previous-symbolic",
            tooltip_text="Previous month" if self.language == "en" else "Предыдущий месяц",
            css_classes=["calendar-nav-button"],
        )
        previous.connect("clicked", self._shift_training_calendar, -1)
        head.append(previous)
        month_label = Gtk.Label(css_classes=["training-calendar-month"])
        months = (
            (
                "January",
                "February",
                "March",
                "April",
                "May",
                "June",
                "July",
                "August",
                "September",
                "October",
                "November",
                "December",
            )
            if self.language == "en"
            else (
                "Январь",
                "Февраль",
                "Март",
                "Апрель",
                "Май",
                "Июнь",
                "Июль",
                "Август",
                "Сентябрь",
                "Октябрь",
                "Ноябрь",
                "Декабрь",
            )
        )
        month_label.set_text(
            f"{months[self.training_calendar_month.month - 1]} {self.training_calendar_month.year}"
        )
        head.append(month_label)
        following = Gtk.Button(
            icon_name="go-next-symbolic",
            tooltip_text="Next month" if self.language == "en" else "Следующий месяц",
            css_classes=["calendar-nav-button"],
        )
        following.connect("clicked", self._shift_training_calendar, 1)
        head.append(following)
        today_button = Gtk.Button(
            label="Today" if self.language == "en" else "Сегодня",
            tooltip_text="Return to the current month"
            if self.language == "en"
            else "Вернуться к текущему месяцу",
            css_classes=["calendar-today-button"],
        )
        today_button.connect("clicked", self._training_calendar_today)
        head.append(today_button)
        card.append(head)

        grid = Gtk.Grid(
            column_spacing=6,
            row_spacing=6,
            column_homogeneous=True,
            css_classes=["training-calendar-grid"],
        )
        weekdays = (
            ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
            if self.language == "en"
            else ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
        )
        for column, weekday in enumerate(weekdays):
            grid.attach(
                Gtk.Label(label=weekday, css_classes=["training-calendar-weekday"]),
                column,
                0,
                1,
                1,
            )
        year = self.training_calendar_month.year
        month = self.training_calendar_month.month
        last_day = pycalendar.monthrange(year, month)[1]
        events = self.app.db.training_calendar(date(year, month, 1), date(year, month, last_day))
        by_day: dict[date, list[sqlite3.Row]] = {}
        for event in events:
            event_day = datetime.fromtimestamp(float(event["created_at"])).date()
            by_day.setdefault(event_day, []).append(event)
        active = self.app.db.active_training()
        weeks = pycalendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
        for row_index, week in enumerate(weeks, 1):
            for column, number in enumerate(week):
                if not number:
                    grid.attach(
                        Gtk.Box(css_classes=["training-calendar-day", "outside"]),
                        column,
                        row_index,
                        1,
                        1,
                    )
                    continue
                day_value = date(year, month, number)
                day_events = by_day.get(day_value, [])
                classes = ["training-calendar-day"]
                if day_value == date.today():
                    classes.append("today")
                if day_events:
                    classes.append("completed")
                cell = Gtk.Box(
                    orientation=Gtk.Orientation.VERTICAL,
                    spacing=5,
                    css_classes=["training-calendar-day-content"],
                )
                cell.append(
                    Gtk.Label(
                        label=str(number),
                        xalign=0,
                        css_classes=["training-calendar-number"],
                    )
                )
                markers = Gtk.Box(spacing=4, css_classes=["training-calendar-markers"])
                tooltips: list[str] = []
                for event in day_events[:4]:
                    course_id = str(event["course_id"])
                    course = COURSES.get(course_id)
                    marker = Gtk.Box(css_classes=["training-calendar-marker", f"course-{course_id}"])
                    markers.append(marker)
                    if course:
                        tooltips.append(
                            f"{training_copy(course, 'title', self.language)} — day {int(event['course_day'])}"
                            if self.language == "en"
                            else f"{training_copy(course, 'title', self.language)} — день {int(event['course_day'])}"
                        )
                if active and day_value == date.today() and not day_events:
                    markers.append(Gtk.Box(css_classes=["training-calendar-marker", "scheduled"]))
                    tooltips.append(
                        "Today’s course day is ready"
                        if self.language == "en"
                        else "Сегодняшний день курса готов"
                    )
                cell.append(markers)
                if tooltips:
                    cell.set_tooltip_text("\n".join(tooltips))
                if day_events:
                    day_button = Gtk.MenuButton(css_classes=classes)
                    day_button.set_child(cell)
                    day_button.set_popover(self._training_calendar_popover(day_value, day_events))
                    day_button.set_tooltip_text("\n".join(tooltips))
                    grid.attach(day_button, column, row_index, 1, 1)
                else:
                    cell.add_css_class("training-calendar-day")
                    for css_class in classes[1:]:
                        cell.add_css_class(css_class)
                    grid.attach(cell, column, row_index, 1, 1)
        card.append(grid)
        if events:
            legend = Gtk.FlowBox(
                selection_mode=Gtk.SelectionMode.NONE,
                column_spacing=12,
                row_spacing=6,
                css_classes=["training-calendar-legend"],
            )
            seen_courses: set[str] = set()
            total_seconds = 0.0
            for event in events:
                total_seconds += float(event["duration_seconds"] or 0)
                course_id = str(event["course_id"])
                if course_id in seen_courses or course_id not in COURSES:
                    continue
                seen_courses.add(course_id)
                item = Gtk.Box(spacing=6)
                item.append(Gtk.Box(css_classes=["training-calendar-marker", f"course-{course_id}"]))
                item.append(
                    Gtk.Label(
                        label=training_copy(COURSES[course_id], "title", self.language),
                        css_classes=["caption"],
                    )
                )
                legend.append(item)
            summary = Gtk.Box(spacing=10, css_classes=["training-calendar-summary"])
            summary.append(legend)
            summary.append(
                Gtk.Label(
                    label=(
                        f"{len(events)} completed · {format_duration(total_seconds, self.language)}"
                        if self.language == "en"
                        else f"Выполнено: {len(events)} · {format_duration(total_seconds, self.language)}"
                    ),
                    hexpand=True,
                    xalign=1,
                    css_classes=["muted", "caption"],
                )
            )
            card.append(summary)
        return card

    def _training_calendar_popover(
        self,
        day_value: date,
        events: list[sqlite3.Row],
    ) -> Gtk.Popover:
        popover = Gtk.Popover(css_classes=["training-calendar-popover"])
        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            css_classes=["training-calendar-popover-content"],
        )
        content.append(
            Gtk.Label(
                label=day_value.strftime("%d.%m.%Y"),
                xalign=0,
                css_classes=["card-title"],
            )
        )
        for event in events:
            course_id = str(event["course_id"])
            course = COURSES.get(course_id)
            if not course:
                continue
            row = Gtk.Box(spacing=9, css_classes=["training-calendar-event-row"])
            row.append(activity_icon(str(course["icon"]), 18))
            copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
            copy.append(
                Gtk.Label(
                    label=training_copy(course, "title", self.language),
                    xalign=0,
                    css_classes=["card-title"],
                )
            )
            copy.append(
                Gtk.Label(
                    label=(
                        f"Course day {int(event['course_day'])} · {format_duration(float(event['duration_seconds']), self.language)}"
                        if self.language == "en"
                        else f"День курса {int(event['course_day'])} · {format_duration(float(event['duration_seconds']), self.language)}"
                    ),
                    xalign=0,
                    css_classes=["muted", "caption"],
                )
            )
            row.append(copy)
            content.append(row)
        popover.set_child(content)
        return popover

    def _shift_training_calendar(self, _button: Gtk.Button, offset: int) -> None:
        month_index = self.training_calendar_month.year * 12 + self.training_calendar_month.month - 1
        month_index += int(offset)
        year, month_zero = divmod(month_index, 12)
        self.training_calendar_month = date(year, month_zero + 1, 1)
        self._rebuild_training()

    def _training_calendar_today(self, _button: Gtk.Button) -> None:
        self.training_calendar_month = date.today().replace(day=1)
        self._rebuild_training()

    def _training_reminder_settings(self) -> Gtk.Widget:
        settings = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=9,
            css_classes=["training-reminder-settings"],
        )
        head = Gtk.Box(spacing=10)
        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        copy.append(
            Gtk.Label(
                label="Workout reminders" if self.language == "en" else "Напоминания о тренировке",
                xalign=0,
                css_classes=["card-title"],
            )
        )
        copy.append(
            Gtk.Label(
                label=(
                    "At a chosen time, reminders repeat hourly. Without a fixed time, they appear every two and a half hours until today’s workout is done."
                    if self.language == "en"
                    else "После выбранного времени напоминание повторяется каждый час. Без фиксированного времени оно приходит раз в два с половиной часа до выполнения тренировки."
                ),
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        head.append(copy)
        enabled = Gtk.Switch(
            active=bool(self.app.config.data.get("training_reminders_enabled", True)),
            valign=Gtk.Align.CENTER,
        )
        head.append(enabled)
        settings.append(head)

        time_row = Gtk.Box(spacing=10, css_classes=["training-reminder-time-row"])
        fixed = Gtk.Switch(
            active=bool(self.app.config.data.get("training_reminder_time")),
            valign=Gtk.Align.CENTER,
        )
        time_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        time_copy.append(
            Gtk.Label(
                label="Use a fixed time" if self.language == "en" else "Использовать точное время",
                xalign=0,
                css_classes=["caption", "training-reminder-time-title"],
            )
        )
        time_copy.append(
            Gtk.Label(
                label=(
                    "Off means a flexible 2.5-hour interval"
                    if self.language == "en"
                    else "Если выключено — гибкий интервал 2,5 часа"
                ),
                xalign=0,
                css_classes=["muted", "caption"],
            )
        )
        time_row.append(fixed)
        time_row.append(time_copy)
        values = [f"{minute // 60:02d}:{minute % 60:02d}" for minute in range(6 * 60, 24 * 60, 30)]
        saved_time = normalize_clock(
            self.app.config.data.get("training_reminder_time"),
            "18:00",
        )
        if saved_time not in values:
            values.append(saved_time)
            values.sort(key=lambda value: tuple(int(part) for part in value.split(":")))
        picker = Gtk.DropDown.new_from_strings(values)
        picker.add_css_class("theme-time-picker")
        picker.set_selected(values.index(saved_time))
        picker.set_valign(Gtk.Align.CENTER)
        time_row.append(picker)
        settings.append(time_row)

        def reset_cycle() -> None:
            if hasattr(self.app, "scheduler"):
                self.app.scheduler.reset_training_reminders()

        def enabled_changed(widget: Gtk.Switch, _pspec: Any) -> None:
            self.app.config.data["training_reminders_enabled"] = widget.get_active()
            self.app.config.save()
            time_row.set_sensitive(widget.get_active())
            reset_cycle()

        def fixed_changed(widget: Gtk.Switch, _pspec: Any) -> None:
            self.app.config.data["training_reminder_time"] = (
                values[picker.get_selected()] if widget.get_active() else None
            )
            self.app.config.save()
            picker.set_sensitive(widget.get_active())
            reset_cycle()

        def time_changed(widget: Gtk.DropDown, _pspec: Any) -> None:
            if not fixed.get_active():
                return
            self.app.config.data["training_reminder_time"] = values[widget.get_selected()]
            self.app.config.save()
            reset_cycle()

        enabled.connect("notify::active", enabled_changed)
        fixed.connect("notify::active", fixed_changed)
        picker.connect("notify::selected", time_changed)
        time_row.set_sensitive(enabled.get_active())
        picker.set_sensitive(fixed.get_active())
        return settings

    def _training_duration_selected(self, button: Gtk.ToggleButton, days: int) -> None:
        if button.get_active():
            self.training_duration_choice = int(days)
            self.app.config.data["training_duration_days"] = int(days)
            self.app.config.save()

    def _training_weekday_selected(self, button: Gtk.ToggleButton, weekday: int) -> None:
        if getattr(self, "_syncing_training_weekdays", False):
            return
        selected = set(self.training_weekdays_choice)
        if button.get_active():
            if len(selected) >= 5:
                self._syncing_training_weekdays = True
                button.set_active(False)
                self._syncing_training_weekdays = False
                return
            selected.add(int(weekday))
        else:
            if len(selected) <= 2:
                self._syncing_training_weekdays = True
                button.set_active(True)
                self._syncing_training_weekdays = False
                return
            selected.discard(int(weekday))
        self.training_weekdays_choice = normalize_weekdays(selected)
        self.training_days_choice = len(self.training_weekdays_choice)
        self.app.config.data["training_weekdays"] = list(self.training_weekdays_choice)
        self.app.config.data["training_days_per_week"] = self.training_days_choice
        self.app.config.save()
        if hasattr(self, "training_weekday_summary"):
            self.training_weekday_summary.set_text(
                f"Selected: {self._weekday_names(self.training_weekdays_choice, short=False)}"
                if self.language == "en"
                else f"Выбрано: {self._weekday_names(self.training_weekdays_choice, short=False)}"
            )

    def _training_level_selected(self, button: Gtk.ToggleButton, level: str) -> None:
        if not button.get_active() or level not in FITNESS_LEVELS:
            return
        self.training_fitness_choice = level
        self.app.config.data["training_fitness_level"] = level
        self.app.config.save()
        if hasattr(self, "training_level_summary"):
            chosen = FITNESS_LEVELS[level]
            self.training_level_summary.set_text(
                f"Selected: {training_copy(chosen, 'title', self.language)}. "
                f"{training_copy(chosen, 'description', self.language)}"
                if self.language == "en"
                else f"Выбрано: {training_copy(chosen, 'title', self.language)}. "
                f"{training_copy(chosen, 'description', self.language)}"
            )

    def _start_training_course(self, _button: Gtk.Button, course_id: str) -> None:
        if course_id not in COURSES:
            return
        active = self.app.db.active_training()
        if active and str(active["course_id"]) == course_id:
            self._training_existing_dialog(active, active_course=True)
            return
        previous = self.app.db.resumable_training(course_id)
        if previous:
            self._training_existing_dialog(previous, active_course=False)
            return
        if active:
            dialog = Adw.MessageDialog.new(
                self,
                "Switch the active course?" if self.language == "en" else "Сменить активный курс?",
                (
                    "Your current course and its completed days will stay in history. Only the new course will remain active."
                    if self.language == "en"
                    else "Текущий курс и выполненные дни останутся в истории. Активным будет только новый курс."
                ),
            )
            dialog.add_response("cancel", "Cancel" if self.language == "en" else "Отмена")
            dialog.add_response("switch", "Switch course" if self.language == "en" else "Сменить курс")
            dialog.set_response_appearance("switch", Adw.ResponseAppearance.SUGGESTED)
            dialog.set_default_response("cancel")
            dialog.set_close_response("cancel")
            dialog.connect(
                "response",
                lambda _dialog, response: (
                    self._create_training_course(course_id) if response == "switch" else None
                ),
            )
            dialog.present()
            return
        self._create_training_course(course_id)

    def _training_existing_dialog(
        self,
        enrollment: sqlite3.Row,
        *,
        active_course: bool,
    ) -> None:
        course = COURSES.get(str(enrollment["course_id"]))
        if not course:
            return
        dialog = Adw.MessageDialog.new(
            self,
            "This course already has progress" if self.language == "en" else "В этом курсе уже есть прогресс",
            (
                f"{training_copy(course, 'title', self.language)} is on day {int(enrollment['current_day'])}. "
                "Continue with its saved settings, or reset it and use the questionnaire choices. Reset permanently removes this course’s completed days. "
                "If another course is active, it will be paused and its history will remain."
                if self.language == "en"
                else f"Курс «{training_copy(course, 'title', self.language)}» находится на дне {int(enrollment['current_day'])}. "
                "Можно продолжить с сохранёнными настройками или сбросить его и применить ответы анкеты. Сброс навсегда удалит выполненные дни этого курса. "
                "Если активен другой курс, он будет поставлен на паузу, а его история сохранится."
            ),
        )
        dialog.add_response("cancel", "Cancel" if self.language == "en" else "Отмена")
        dialog.add_response("continue", "Continue course" if self.language == "en" else "Продолжить курс")
        dialog.add_response("reset", "Reset progress" if self.language == "en" else "Сбросить прогресс")
        dialog.set_response_appearance("continue", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def respond(_dialog: Adw.MessageDialog, response: str) -> None:
            if response == "continue":
                if active_course:
                    self._show_active_training()
                else:
                    self.app.db.resume_training(int(enrollment["id"]))
                    self.app.scheduler.reset_training_reminders()
                    self._rebuild_active_training_at_top()
            elif response == "reset":
                self.app.db.reset_training(
                    int(enrollment["id"]),
                    duration_days=self.training_duration_choice,
                    fitness_level=self.training_fitness_choice,
                    days_per_week=self.training_days_choice,
                    weekdays=self.training_weekdays_choice,
                )
                self.app.scheduler.reset_training_reminders()
                self._reset_training_timer()
                self._rebuild_active_training_at_top()

        dialog.connect("response", respond)
        dialog.present()

    def _create_training_course(self, course_id: str) -> None:
        self.app.db.start_training(
            course_id,
            self.training_duration_choice,
            self.training_fitness_choice,
            self.training_days_choice,
            weekdays=self.training_weekdays_choice,
        )
        self.app.scheduler.reset_training_reminders()
        self._reset_training_timer()
        self._rebuild_active_training_at_top()

    def _edit_active_training_days(self, _button: Gtk.Button) -> None:
        enrollment = self.app.db.active_training()
        if not enrollment:
            return
        enrollment_id = int(enrollment["id"])
        selected = set(self._enrollment_weekdays(enrollment))
        selected_level = {"value": str(enrollment["fitness_level"])}
        dialog = Adw.MessageDialog.new(
            self,
            "Edit active plan" if self.language == "en" else "Изменить активный план",
            (
                "Choose two to five days. The new rhythm applies immediately; completed days and course progress stay unchanged."
                if self.language == "en"
                else "Выберите от двух до пяти дней. Новое расписание применяется сразу; выполненные дни и прогресс курса сохранятся."
            ),
        )
        form = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            css_classes=["training-edit-days"],
        )
        weekday_options = Gtk.Box(
            spacing=6,
            homogeneous=True,
            css_classes=["training-weekly-options"],
        )
        short_names = (
            ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
            if self.language == "en"
            else ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
        )
        full_names = (
            ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
            if self.language == "en"
            else ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")
        )
        summary = Gtk.Label(xalign=0, wrap=True, css_classes=["muted", "caption"])
        syncing = {"value": False}

        def update_summary() -> None:
            prefix = "Selected" if self.language == "en" else "Выбрано"
            summary.set_text(f"{prefix}: {self._weekday_names(selected, short=False)}")

        def toggle_day(button: Gtk.ToggleButton, weekday: int) -> None:
            if syncing["value"]:
                return
            if button.get_active():
                if len(selected) >= 5:
                    syncing["value"] = True
                    button.set_active(False)
                    syncing["value"] = False
                    return
                selected.add(weekday)
            else:
                if len(selected) <= 2:
                    syncing["value"] = True
                    button.set_active(True)
                    syncing["value"] = False
                    return
                selected.discard(weekday)
            update_summary()

        for weekday, label in enumerate(short_names):
            day_button = Gtk.ToggleButton(
                label=label,
                tooltip_text=full_names[weekday],
                css_classes=["training-duration-button", "training-weekday-button"],
            )
            day_button.set_active(weekday in selected)
            day_button.connect("toggled", toggle_day, weekday)
            weekday_options.append(day_button)
        form.append(weekday_options)
        update_summary()
        form.append(summary)
        form.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        form.append(
            Gtk.Label(
                label="Preparation level" if self.language == "en" else "Уровень подготовки",
                xalign=0,
                css_classes=["card-title"],
            )
        )
        level_options = Gtk.Box(
            spacing=6,
            homogeneous=True,
            css_classes=["training-edit-levels"],
        )
        first_level: Gtk.ToggleButton | None = None
        for level_id, level in FITNESS_LEVELS.items():
            level_button = Gtk.ToggleButton(
                label=training_copy(level, "short", self.language),
                tooltip_text=training_copy(level, "title", self.language),
                css_classes=["training-duration-button", "training-edit-level-button"],
            )
            if first_level is None:
                first_level = level_button
            else:
                level_button.set_group(first_level)
            level_button.set_active(level_id == selected_level["value"])

            def level_changed(button: Gtk.ToggleButton, value: str) -> None:
                if button.get_active():
                    selected_level["value"] = value

            level_button.connect("toggled", level_changed, level_id)
            level_options.append(level_button)
        form.append(level_options)
        dialog.set_extra_child(form)
        dialog.add_response("cancel", "Cancel" if self.language == "en" else "Отмена")
        dialog.add_response("save", "Save plan" if self.language == "en" else "Сохранить план")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def respond(_dialog: Adw.MessageDialog, response: str) -> None:
            if response != "save":
                return
            updated = self.app.db.update_training_plan(
                enrollment_id,
                weekdays=selected,
                fitness_level=selected_level["value"],
            )
            saved_weekdays = self._enrollment_weekdays(updated)
            self.training_weekdays_choice = saved_weekdays
            self.training_days_choice = len(saved_weekdays)
            self.training_fitness_choice = str(updated["fitness_level"])
            self.app.config.data["training_weekdays"] = list(saved_weekdays)
            self.app.config.data["training_days_per_week"] = len(saved_weekdays)
            self.app.config.data["training_fitness_level"] = self.training_fitness_choice
            self.app.config.save()
            self.app.scheduler.reset_training_reminders()
            self.training_session_token = None
            self._reset_training_timer()
            self._rebuild_training()

        dialog.connect("response", respond)
        dialog.present()

    def _render_active_training(self, enrollment: sqlite3.Row) -> None:
        course_id = str(enrollment["course_id"])
        course = COURSES.get(course_id)
        if not course:
            return
        enrollment_id = int(enrollment["id"])
        course_day = int(enrollment["current_day"])
        total_days = int(enrollment["duration_days"])
        fitness_level = str(enrollment["fitness_level"])
        weekdays = self._enrollment_weekdays(enrollment)
        days_per_week = len(weekdays)
        start_weekday = datetime.fromtimestamp(float(enrollment["started_at"])).weekday()
        token = (enrollment_id, course_day)
        if self.training_session_token != token:
            self._reset_training_timer()
            self.training_session_token = token
        plan = training_day(
            course_id,
            course_day,
            total_days,
            self.language,
            fitness_level,
            days_per_week,
            weekdays,
            start_weekday,
        )
        summary = self.app.db.training_summary(enrollment_id)
        self.training_active_plan = plan
        self.training_active_enrollment = enrollment_id
        self.training_available = self.app.db.training_available_today(enrollment_id)

        back = Gtk.Button(
            label="Change course" if self.language == "en" else "Сменить курс",
            halign=Gtk.Align.START,
            css_classes=["data-button", "training-back-button"],
        )
        back.connect("clicked", self._show_training_catalog)
        self.training_body.append(back)

        hero = self._responsive_flow("training-active-hero-flow", columns=2, spacing=18)
        hero.add_css_class("training-active-hero")
        hero.append(
            self._training_course_visual(
                course,
                active=True,
                days_per_week=days_per_week,
                weekdays=weekdays,
            )
        )
        hero_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9, hexpand=True)
        hero_copy.append(
            Gtk.Label(
                label="ACTIVE COURSE" if self.language == "en" else "АКТИВНЫЙ КУРС",
                xalign=0,
                css_classes=["training-kicker"],
            )
        )
        hero_copy.append(
            Gtk.Label(
                label=training_copy(course, "title", self.language),
                xalign=0,
                wrap=True,
                css_classes=["training-active-title"],
            )
        )
        hero_copy.append(
            Gtk.Label(
                label=training_copy(course, "description", self.language),
                xalign=0,
                wrap=True,
                css_classes=["training-active-copy"],
            )
        )
        progress_head = Gtk.Box(spacing=8)
        progress_head.append(
            Gtk.Label(
                label=(
                    f"Day {course_day} of {total_days}"
                    if self.language == "en"
                    else f"День {course_day} из {total_days}"
                ),
                xalign=0,
                hexpand=True,
                css_classes=["training-progress-label"],
            )
        )
        progress_head.append(
            Gtk.Label(
                label=f"{round((course_day - 1) * 100 / total_days)}%",
                css_classes=["training-progress-label"],
            )
        )
        hero_copy.append(progress_head)
        hero_copy.append(
            Gtk.ProgressBar(
                fraction=max(0.0, min(1.0, (course_day - 1) / total_days)),
                css_classes=["training-course-progress"],
            )
        )
        hero_actions = Gtk.Box(
            spacing=8,
            halign=Gtk.Align.END,
            css_classes=["training-hero-actions"],
        )
        edit_days = Gtk.Button(
            label="Edit plan" if self.language == "en" else "Настроить план",
            css_classes=["training-edit-days-button"],
        )
        edit_days.connect("clicked", self._edit_active_training_days)
        hero_actions.append(edit_days)
        hero_action = Gtk.Button(
            label=(
                "Start today's workout"
                if plan["kind"] != "rest" and self.language == "en"
                else "Начать тренировку"
                if plan["kind"] != "rest"
                else "Confirm rest day"
                if self.language == "en"
                else "Подтвердить день отдыха"
            ),
            css_classes=["health-primary", "training-hero-action"],
        )
        if plan["kind"] == "rest":
            hero_action.connect("clicked", self._complete_training_session)
        else:
            hero_action.connect("clicked", self._launch_training_session)
        hero_action.set_sensitive(self.training_available)
        if not self.training_available:
            hero_action.set_label(
                "Next day opens tomorrow" if self.language == "en" else "Следующий день откроется завтра"
            )
        hero_actions.append(hero_action)
        hero_copy.append(hero_actions)
        hero.append(hero_copy)
        self.training_body.append(hero)

        metrics = self._stack_when_compact(Gtk.Box(spacing=10, homogeneous=True))
        completed_days = int(summary["completed_days"] or 0)
        if plan["lighter"]:
            phase_note = (
                f"{plan['fitness_title']} · lighter week"
                if self.language == "en"
                else f"{plan['fitness_title']} · облегчённая неделя"
            )
        elif plan["kind"] == "strength":
            phase_note = (
                f"{plan['fitness_title']} · load step {int(plan['build_step']) + 1}"
                if self.language == "en"
                else f"{plan['fitness_title']} · ступень нагрузки {int(plan['build_step']) + 1}"
            )
        else:
            phase_note = str(plan["fitness_title"])
        for title, value, note in (
            (
                "Completed" if self.language == "en" else "Завершено",
                str(completed_days),
                "course days" if self.language == "en" else "дней курса",
            ),
            (
                "Practice" if self.language == "en" else "Практика",
                format_duration(float(summary["duration_seconds"] or 0), self.language),
                "recorded time" if self.language == "en" else "учтённое время",
            ),
            (
                "Current phase" if self.language == "en" else "Текущий этап",
                str(plan["phase_name"]),
                phase_note,
            ),
        ):
            metric = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=4,
                css_classes=["card", "training-metric"],
            )
            metric.append(Gtk.Label(label=title, xalign=0, wrap=True, css_classes=["metric-label"]))
            metric.append(Gtk.Label(label=value, xalign=0, wrap=True, css_classes=["metric-value"]))
            metric.append(Gtk.Label(label=note, xalign=0, wrap=True, css_classes=["muted", "caption"]))
            metrics.append(metric)
        self.training_body.append(metrics)

        session = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            css_classes=["card", "training-session-card"],
        )
        session_head = Gtk.Box(spacing=10)
        session_title = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        session_title.append(Gtk.Label(label=str(plan["title"]), xalign=0, css_classes=["section-title"]))
        session_title.append(
            Gtk.Label(
                label=str(plan["description"]),
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        session_head.append(session_title)
        if int(plan["estimated_seconds"]) > 0:
            session_head.append(
                Gtk.Label(
                    label=(
                        f"about {format_duration(plan['estimated_seconds'], self.language)}"
                        if self.language == "en"
                        else f"около {format_duration(plan['estimated_seconds'], self.language)}"
                    ),
                    valign=Gtk.Align.START,
                    css_classes=["training-time-chip"],
                )
            )
        session.append(session_head)
        if plan["kind"] == "strength" and int(plan["rounds"]) > 1:
            session.append(
                Gtk.Label(
                    label=(
                        f"Complete {plan['rounds']} calm rounds. Rest as needed between exercises."
                        if self.language == "en"
                        else f"Выполните {plan['rounds']} спокойных круга. Между упражнениями отдыхайте по самочувствию."
                    ),
                    xalign=0,
                    wrap=True,
                    css_classes=["training-round-note"],
                )
            )
        for index, exercise in enumerate(plan["exercises"], 1):
            session.append(self._training_exercise_row(index, exercise))
        if not plan["exercises"]:
            rest = Gtk.Box(spacing=10, css_classes=["training-rest-message"])
            rest.append(activity_icon("breathing", 22))
            rest.append(
                Gtk.Label(
                    label=(
                        "There is no timer today. Mark the day when you have taken the planned rest."
                        if self.language == "en"
                        else "Сегодня таймер не нужен. Отметьте день после запланированного отдыха."
                    ),
                    xalign=0,
                    wrap=True,
                    hexpand=True,
                )
            )
            session.append(rest)

        self.training_body.append(session)
        self.training_body.append(self._training_safety_card())
        reminder_settings = self._training_reminder_settings()
        reminder_settings.add_css_class("card")
        reminder_settings.add_css_class("training-active-reminders")
        self.training_body.append(reminder_settings)

        schedule = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=9,
            css_classes=["card", "training-schedule-card"],
        )
        schedule.append(
            Gtk.Label(
                label="Next course days" if self.language == "en" else "Ближайшие дни курса",
                xalign=0,
                css_classes=["section-title"],
            )
        )
        days_flow = self._responsive_flow("training-days-flow", columns=7, spacing=7)
        self._building_page_breakpoint.add_setter(days_flow, "max-children-per-line", 2)
        for item in upcoming_days(
            course_id,
            course_day,
            total_days,
            self.language,
            fitness_level=fitness_level,
            days_per_week=days_per_week,
            weekdays=weekdays,
            start_weekday=start_weekday,
        ):
            chip = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=3,
                css_classes=["training-day-chip", f"training-day-{item['kind']}"],
            )
            if int(item["course_day"]) == course_day:
                chip.add_css_class("current")
            chip.append(
                Gtk.Label(
                    label=(
                        f"Day {item['course_day']}" if self.language == "en" else f"День {item['course_day']}"
                    ),
                    css_classes=["training-day-number"],
                )
            )
            chip.append(
                Gtk.Label(
                    label=str(item["title"]),
                    wrap=True,
                    justify=Gtk.Justification.CENTER,
                    css_classes=["caption"],
                )
            )
            days_flow.append(chip)
        schedule.append(days_flow)
        self.training_body.append(schedule)

        actions = Gtk.Box(spacing=8, halign=Gtk.Align.END, css_classes=["training-course-actions"])
        reset_button = Gtk.Button(
            label="Reset progress" if self.language == "en" else "Сбросить прогресс",
            css_classes=["data-button", "training-reset-button"],
        )
        reset_button.connect("clicked", self._confirm_reset_active_training, enrollment_id)
        actions.append(reset_button)
        end_button = Gtk.Button(
            label="End course" if self.language == "en" else "Завершить курс досрочно",
            css_classes=["data-button", "training-end-button"],
        )
        end_button.connect("clicked", self._confirm_end_training, enrollment_id)
        actions.append(end_button)
        self.training_body.append(actions)
        self.training_body.append(self._training_calendar_card())

    def _training_exercise_row(self, index: int, exercise: dict[str, Any]) -> Gtk.Widget:
        row = Gtk.Box(spacing=11, css_classes=["training-exercise-row"])
        markers = Gtk.Box(spacing=7, valign=Gtk.Align.CENTER, css_classes=["training-row-markers"])
        markers.append(
            Gtk.Label(
                label=str(index),
                valign=Gtk.Align.CENTER,
                css_classes=["training-exercise-number"],
            )
        )
        icon = activity_icon(str(exercise["icon"]), 21, "training-exercise-icon")
        icon.set_valign(Gtk.Align.CENTER)
        markers.append(icon)
        row.append(markers)
        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        head = Gtk.Box(spacing=8)
        head.append(
            Gtk.Label(
                label=str(exercise["title"]),
                xalign=0,
                hexpand=True,
                wrap=True,
                css_classes=["card-title"],
            )
        )
        head.append(Gtk.Label(label=str(exercise["target"]), css_classes=["training-target-chip"]))
        copy.append(head)
        copy.append(
            Gtk.Label(
                label=str(exercise["instruction"]),
                xalign=0,
                wrap=True,
                css_classes=["training-exercise-copy"],
            )
        )
        copy.append(
            Gtk.Label(
                label=str(exercise["cue"]),
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        row.append(copy)
        return row

    def _reset_training_timer(self) -> None:
        self.training_running = False
        self.training_elapsed = 0.0
        if self.training_timer_source is not None:
            GLib.source_remove(self.training_timer_source)
            self.training_timer_source = None

    def _launch_training_session(self, _button: Gtk.Button) -> None:
        plan = getattr(self, "training_active_plan", None)
        enrollment_id = getattr(self, "training_active_enrollment", None)
        if not plan or enrollment_id is None or not self.training_available or not plan.get("exercises"):
            return
        course = COURSES.get(str(plan["course_id"]))
        if not course:
            return
        overlay = TrainingSessionOverlay(
            self.app,
            plan,
            course,
            self._finish_training_day,
        )
        overlay.set_transient_for(self)
        self.training_overlay = overlay
        overlay.present()

    def _complete_training_session(self, _button: Gtk.Button) -> None:
        self._finish_training_day(0.0)

    def _finish_training_day(self, duration_seconds: float) -> None:
        plan = getattr(self, "training_active_plan", None)
        enrollment_id = getattr(self, "training_active_enrollment", None)
        if not plan or enrollment_id is None:
            return
        if plan["kind"] != "rest" and duration_seconds <= 0:
            return
        final_day = self.app.db.complete_training_day(
            enrollment_id,
            int(plan["course_day"]),
            str(plan["session_key"]),
            duration_seconds,
        )
        self._reset_training_timer()
        self.training_session_token = None
        if self.language == "en":
            title = "Course complete" if final_day else "Training day complete"
        else:
            title = "Курс завершён" if final_day else "День курса завершён"
        body = (
            "The full course is in your history. Keep only the routine that continues to feel useful."
            if final_day and self.language == "en"
            else "Курс сохранён в истории. Оставляйте только ту нагрузку, которая продолжает быть полезной."
            if final_day
            else f"Day {plan['course_day']} is saved. The next course day opens tomorrow."
            if self.language == "en"
            else f"День {plan['course_day']} сохранён. Следующий день курса откроется завтра."
        )
        self.app.push_app_notification(
            "training",
            title,
            body,
            "training",
            notification_id=f"training-{enrollment_id}-{plan['course_day']}",
            button="Open training" if self.language == "en" else "Открыть тренировки",
        )
        play_guidance_sound(self.app.config.data, "done")
        self._rebuild_training()

    def _confirm_end_training(self, _button: Gtk.Button, enrollment_id: int) -> None:
        dialog = Adw.MessageDialog.new(
            self,
            "End this course?" if self.language == "en" else "Завершить этот курс?",
            (
                "Completed days stay in history. You can start another course afterwards."
                if self.language == "en"
                else "Выполненные дни останутся в истории. После этого можно начать другой курс."
            ),
        )
        dialog.add_response("cancel", "Cancel" if self.language == "en" else "Отмена")
        dialog.add_response("end", "End course" if self.language == "en" else "Завершить курс")
        dialog.set_response_appearance("end", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect(
            "response",
            lambda _dialog, response: self._end_training(enrollment_id) if response == "end" else None,
        )
        dialog.present()

    def _confirm_reset_active_training(self, _button: Gtk.Button, enrollment_id: int) -> None:
        dialog = Adw.MessageDialog.new(
            self,
            "Reset all course progress?" if self.language == "en" else "Сбросить весь прогресс курса?",
            (
                "Every completed day and recorded minute in this course will be permanently removed. Calendar entries for this course will disappear."
                if self.language == "en"
                else "Все выполненные дни и учтённые минуты этого курса будут удалены безвозвратно. Отметки этого курса исчезнут из календаря."
            ),
        )
        dialog.add_response("cancel", "Cancel" if self.language == "en" else "Отмена")
        dialog.add_response("reset", "Reset progress" if self.language == "en" else "Сбросить прогресс")
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect(
            "response",
            lambda _dialog, response: (
                self._reset_active_training(enrollment_id) if response == "reset" else None
            ),
        )
        dialog.present()

    def _reset_active_training(self, enrollment_id: int) -> None:
        self.app.db.reset_training(enrollment_id)
        self._reset_training_timer()
        self.training_session_token = None
        self._rebuild_active_training_at_top()

    def _end_training(self, enrollment_id: int) -> None:
        self.app.db.stop_training(enrollment_id)
        self._reset_training_timer()
        self.training_session_token = None
        self._rebuild_training()

    def _build_habits(self) -> Gtk.Widget:
        scroller, content = self._page()
        head = self._stack_when_compact(Gtk.Box(spacing=10))
        heading = self._heading(
            "Полезные привычки",
            "Небольшие дневные цели с локальной историей и необязательными напоминаниями.",
        )
        heading.set_hexpand(True)
        head.append(heading)
        add_button = Gtk.Button(
            label=self._t("Добавить привычку"),
            css_classes=["health-primary"],
            valign=Gtk.Align.END,
        )
        add_button.connect("clicked", self._show_habit_editor, None)
        head.append(add_button)
        content.append(head)
        summary = self._stack_when_compact(Gtk.Box(spacing=10, homogeneous=True))
        self.habits_done_value = Gtk.Label(xalign=0, css_classes=["metric-value"])
        self.habits_active_value = Gtk.Label(xalign=0, css_classes=["metric-value"])
        self.habits_week_value = Gtk.Label(xalign=0, css_classes=["metric-value"])
        for title, value, hint in (
            ("Сегодня", self.habits_done_value, "дневных целей выполнено"),
            ("Активные", self.habits_active_value, "привычки в вашем плане"),
            ("За 7 дней", self.habits_week_value, "всего отметок"),
        ):
            summary.append(self._metric_card(title, value, hint))
        content.append(summary)
        self.habit_list = Gtk.FlowBox(css_classes=["habit-flow"])
        self.habit_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.habit_list.set_min_children_per_line(1)
        self.habit_list.set_max_children_per_line(2)
        self.habit_list.set_column_spacing(10)
        self.habit_list.set_row_spacing(10)
        self.habit_list.set_homogeneous(True)
        content.append(self.habit_list)
        self._rebuild_habits()
        return scroller

    def _rebuild_habits(self) -> None:
        if not hasattr(self, "habit_list"):
            return
        clear_box(self.habit_list)
        habits = [item for item in self.app.config.data.get("habits", []) if isinstance(item, dict)]
        active = [item for item in habits if item.get("enabled")]
        completed_goals = 0
        week_marks = 0
        for habit in habits:
            habit_id = str(habit.get("id") or "")
            target = max(1, int(habit.get("target", 1)))
            count = self.app.db.habit_count(habit_id)
            week_marks += self.app.db.habit_week_count(habit_id)
            if habit.get("enabled") and count >= target:
                completed_goals += 1
            card = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=9,
                css_classes=["card", "habit-card"],
            )
            head = Gtk.Box(spacing=10)
            icon = str(habit.get("icon") or "general")
            head.append(activity_icon(icon if icon in REMINDER_META else "general", 22, "habit-icon-shell"))
            copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
            copy.append(
                Gtk.Label(
                    label=self._t(str(habit.get("title") or "Полезная привычка")),
                    xalign=0,
                    wrap=True,
                    css_classes=["settings-title"],
                )
            )
            streak = self.app.db.habit_streak(habit_id, target)
            copy.append(
                Gtk.Label(
                    label=(
                        (
                            f"Streak: {streak} day{'s' if streak != 1 else ''}"
                            if self.language == "en"
                            else f"Серия: {streak} дн."
                        )
                        if streak
                        else ("No streak yet" if self.language == "en" else "Серия начнётся после выполнения")
                    ),
                    xalign=0,
                    css_classes=["muted", "caption"],
                )
            )
            head.append(copy)
            enabled = Gtk.Switch(active=bool(habit.get("enabled")), valign=Gtk.Align.CENTER)
            enabled.connect("notify::active", self._habit_enabled_changed, habit_id)
            head.append(enabled)
            card.append(head)
            progress_head = Gtk.Box(spacing=8)
            progress_head.append(
                Gtk.Label(
                    label="Today" if self.language == "en" else "Сегодня",
                    xalign=0,
                    hexpand=True,
                    css_classes=["muted", "caption"],
                )
            )
            progress_head.append(
                Gtk.Label(label=f"{min(count, target)} / {target}", css_classes=["habit-progress-value"])
            )
            card.append(progress_head)
            progress = Gtk.ProgressBar(fraction=min(1.0, count / target), css_classes=["habit-progress"])
            card.append(progress)
            reminder_row = Gtk.Box(spacing=7)
            reminder_row.append(Gtk.Image.new_from_icon_name("alarm-symbolic"))
            reminder_row.append(
                Gtk.Label(
                    label=(
                        (
                            f"Reminder at {habit.get('reminder_time', '18:00')}"
                            if self.language == "en"
                            else f"Напоминание в {habit.get('reminder_time', '18:00')}"
                        )
                        if habit.get("reminder_enabled")
                        else ("Reminder is off" if self.language == "en" else "Напоминание выключено")
                    ),
                    xalign=0,
                    hexpand=True,
                    css_classes=["muted", "caption"],
                )
            )
            reminder_switch = Gtk.Switch(
                active=bool(habit.get("reminder_enabled")),
                sensitive=bool(habit.get("enabled")),
                valign=Gtk.Align.CENTER,
            )
            reminder_switch.connect("notify::active", self._habit_reminder_changed, habit_id)
            reminder_row.append(reminder_switch)
            card.append(reminder_row)
            actions = Gtk.Grid(column_spacing=7, row_spacing=7, column_homogeneous=True)
            undo = Gtk.Button(
                label="Undo" if self.language == "en" else "Отменить",
                css_classes=["data-button"],
                sensitive=count > 0,
            )
            undo.connect("clicked", self._habit_mark, habit_id, -1)
            edit = Gtk.Button(label=self._t("Изменить"), css_classes=["data-button"])
            edit.connect("clicked", self._show_habit_editor, habit_id)
            done = Gtk.Button(
                label=(
                    "Completed"
                    if count >= target and self.language == "en"
                    else "Выполнено"
                    if count >= target
                    else "Mark done"
                    if self.language == "en"
                    else "Отметить"
                ),
                css_classes=["health-primary", "habit-done-button"],
                sensitive=bool(habit.get("enabled")) and count < target,
                hexpand=True,
            )
            done.connect("clicked", self._habit_mark, habit_id, 1)
            actions.attach(undo, 0, 0, 1, 1)
            actions.attach(edit, 1, 0, 1, 1)
            actions.attach(done, 0, 1, 2, 1)
            card.append(actions)
            card.set_opacity(1.0 if habit.get("enabled") else 0.58)
            self.habit_list.append(card)
        self.habits_done_value.set_text(f"{completed_goals} / {len(active)}")
        self.habits_active_value.set_text(str(len(active)))
        self.habits_week_value.set_text(str(week_marks))

    def _find_habit(self, habit_id: str) -> dict[str, Any] | None:
        return next(
            (
                item
                for item in self.app.config.data.get("habits", [])
                if isinstance(item, dict) and item.get("id") == habit_id
            ),
            None,
        )

    def _habit_mark(self, _button: Gtk.Button, habit_id: str, amount: int) -> None:
        habit = self._find_habit(habit_id)
        if not habit:
            return
        count = self.app.db.habit_count(habit_id)
        target = max(1, int(habit.get("target", 1)))
        if amount > 0 and count >= target:
            return
        if amount < 0 and count <= 0:
            return
        self.app.db.log_habit(habit_id, amount)
        self._rebuild_habits()

    def _habit_enabled_changed(self, switch: Gtk.Switch, _pspec: Any, habit_id: str) -> None:
        habit = self._find_habit(habit_id)
        if habit:
            habit["enabled"] = switch.get_active()
            if not switch.get_active():
                habit["reminder_enabled"] = False
            self.app.config.save()
            self._rebuild_habits()

    def _habit_reminder_changed(self, switch: Gtk.Switch, _pspec: Any, habit_id: str) -> None:
        habit = self._find_habit(habit_id)
        if habit:
            habit["reminder_enabled"] = switch.get_active()
            self.app.config.save()
            self._rebuild_habits()

    def _show_habit_editor(self, _button: Gtk.Button, habit_id: str | None) -> None:
        habit = self._find_habit(habit_id) if habit_id else None
        dialog = Adw.MessageDialog.new(
            self,
            (
                "Edit habit"
                if habit and self.language == "en"
                else "Изменить привычку"
                if habit
                else "New habit"
                if self.language == "en"
                else "Новая привычка"
            ),
            (
                "Set a realistic daily target and one optional reminder."
                if self.language == "en"
                else "Задайте реалистичную дневную цель и одно необязательное напоминание."
            ),
        )
        form = Gtk.Grid(column_spacing=10, row_spacing=10, css_classes=["habit-editor"])
        title_entry = Gtk.Entry(
            text=str(habit.get("title") if habit else ""),
            placeholder_text="Habit name" if self.language == "en" else "Название привычки",
            hexpand=True,
        )
        target_spin = Gtk.SpinButton.new_with_range(1, 10, 1)
        target_spin.set_value(float(habit.get("target", 1) if habit else 1))
        reminder_enabled = Gtk.Switch(active=bool(habit.get("reminder_enabled", False) if habit else False))
        time_value = str(habit.get("reminder_time", "18:00") if habit else "18:00")
        hour, minute = (int(part) for part in time_value.split(":", 1))
        hour_spin = Gtk.SpinButton.new_with_range(0, 23, 1)
        minute_spin = Gtk.SpinButton.new_with_range(0, 59, 5)
        hour_spin.set_value(hour)
        minute_spin.set_value(minute)
        time_box = Gtk.Box(spacing=5)
        time_box.append(hour_spin)
        time_box.append(Gtk.Label(label=":"))
        time_box.append(minute_spin)
        for row, (label, widget) in enumerate(
            (
                ("Название" if self.language != "en" else "Name", title_entry),
                ("Цель в день" if self.language != "en" else "Daily target", target_spin),
                ("Напоминать" if self.language != "en" else "Reminder", reminder_enabled),
                ("Время" if self.language != "en" else "Time", time_box),
            )
        ):
            form.attach(Gtk.Label(label=label, xalign=0, css_classes=["muted"]), 0, row, 1, 1)
            form.attach(widget, 1, row, 1, 1)
        dialog.set_extra_child(form)
        dialog.add_response("cancel", "Cancel" if self.language == "en" else "Отмена")
        if habit:
            dialog.add_response("delete", "Delete" if self.language == "en" else "Удалить")
            dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.add_response("save", "Save" if self.language == "en" else "Сохранить")
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)

        def save_habit(_dialog: Adw.MessageDialog, response: str) -> None:
            if response == "delete" and habit:
                self.app.config.data["habits"] = [
                    item for item in self.app.config.data.get("habits", []) if item.get("id") != habit_id
                ]
            elif response == "save":
                title = title_entry.get_text().strip()
                if not title:
                    return
                target_habit = habit or {
                    "id": f"habit-{int(time.time() * 1000)}",
                    "enabled": True,
                    "icon": "general",
                }
                target_habit.update(
                    {
                        "title": title[:80],
                        "target": int(target_spin.get_value()),
                        "reminder_enabled": reminder_enabled.get_active(),
                        "reminder_time": f"{int(hour_spin.get_value()):02d}:{int(minute_spin.get_value()):02d}",
                    }
                )
                if habit is None:
                    self.app.config.data.setdefault("habits", []).append(target_habit)
            else:
                return
            self.app.config.save()
            self._rebuild_habits()

        dialog.connect("response", save_habit)
        dialog.present()

    def _build_achievements(self) -> Gtk.Widget:
        scroller, content = self._page()
        content.append(
            self._heading(
                "Achievements" if self.language == "en" else "Достижения",
                (
                    "A record of consistency, not a competition. Every emblem is earned by completed activities."
                    if self.language == "en"
                    else "История регулярности, а не соревнование. Каждая эмблема открывается за выполненные активности."
                ),
            )
        )
        summary = Gtk.Grid(column_spacing=10, column_homogeneous=True)
        self.achievement_unlocked_value = Gtk.Label(xalign=0, css_classes=["metric-value"])
        self.achievement_series_value = Gtk.Label(xalign=0, css_classes=["metric-value"])
        self.achievement_streak_value = Gtk.Label(xalign=0, css_classes=["metric-value"])
        for column, (title, value, hint) in enumerate(
            (
                (
                    "Emblems" if self.language == "en" else "Эмблемы",
                    self.achievement_unlocked_value,
                    "unlocked" if self.language == "en" else "открыто",
                ),
                (
                    "Series" if self.language == "en" else "Серии",
                    self.achievement_series_value,
                    "fully completed" if self.language == "en" else "полностью завершено",
                ),
                (
                    "Best rhythm" if self.language == "en" else "Лучший ритм",
                    self.achievement_streak_value,
                    "consecutive days" if self.language == "en" else "дней подряд",
                ),
            )
        ):
            summary.attach(self._metric_card(title, value, hint), column, 0, 1, 1)
        content.append(summary)
        self.achievement_series_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            css_classes=["achievement-series-list"],
        )
        content.append(self.achievement_series_box)
        self._rebuild_achievements()
        return scroller

    def _rebuild_achievements(self) -> None:
        if not hasattr(self, "achievement_series_box"):
            return
        clear_box(self.achievement_series_box)
        achievements = self.app.db.achievement_progress()
        unlocked_total = sum(item["unlocked_at"] is not None for item in achievements)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for achievement in achievements:
            grouped.setdefault(str(achievement["series"]), []).append(achievement)
        completed_series = sum(
            all(item["unlocked_at"] is not None for item in series) for series in grouped.values()
        )
        metrics = self.app.db.achievement_metrics()
        self.achievement_unlocked_value.set_text(f"{unlocked_total} / {len(achievements)}")
        self.achievement_series_value.set_text(f"{completed_series} / {len(grouped)}")
        self.achievement_streak_value.set_text(str(metrics["break_streak"]))
        for series in grouped.values():
            first = series[0]
            unlocked_in_series = sum(item["unlocked_at"] is not None for item in series)
            series_card = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=12,
                css_classes=["card", "achievement-series-card"],
            )
            header = Gtk.Box(spacing=10)
            header.append(
                Gtk.Label(
                    label=str(first[f"title_{self.language}"]),
                    xalign=0,
                    hexpand=True,
                    css_classes=["section-title"],
                )
            )
            header.append(
                Gtk.Label(
                    label=f"{unlocked_in_series} / {len(series)}",
                    css_classes=["achievement-series-count"],
                )
            )
            series_card.append(header)
            levels = self._responsive_flow("achievement-levels", columns=4)
            # Eight levels only have balanced 4 x 2 and 2 x 4 layouts. Letting
            # FlowBox choose three columns creates a partial third row and makes
            # the fixed responsive height clip cards at intermediate widths.
            levels.set_min_children_per_line(4)
            levels_frame = Adw.BreakpointBin()
            levels_frame.set_size_request(360, 464)
            levels_frame.set_child(levels)
            levels_breakpoint = Adw.Breakpoint()
            levels_breakpoint.set_condition(Adw.BreakpointCondition.parse("max-width: 850sp"))
            levels_breakpoint.add_setter(levels, "min-children-per-line", 2)
            levels_breakpoint.add_setter(levels, "max-children-per-line", 2)
            levels_breakpoint.add_setter(levels_frame, "height-request", 938)
            levels_frame.add_breakpoint(levels_breakpoint)
            next_locked_seen = False
            for achievement in series:
                unlocked_at = achievement["unlocked_at"]
                is_unlocked = unlocked_at is not None
                is_next = not is_unlocked and not next_locked_seen
                if not is_unlocked:
                    next_locked_seen = True
                level = Gtk.Box(
                    orientation=Gtk.Orientation.VERTICAL,
                    spacing=7,
                    halign=Gtk.Align.FILL,
                    css_classes=[
                        "achievement-level",
                        "unlocked" if is_unlocked else "next" if is_next else "locked",
                    ],
                )
                level.append(
                    achievement_emblem(
                        str(achievement["icon"]),
                        str(achievement["tone"]),
                        int(achievement["level"]),
                        is_unlocked,
                    )
                )
                level.append(
                    Gtk.Label(
                        label=(
                            f"Level {achievement_level_mark(int(achievement['level']))}"
                            if self.language == "en"
                            else f"Уровень {achievement_level_mark(int(achievement['level']))}"
                        ),
                        css_classes=["achievement-level-title"],
                    )
                )
                level.append(
                    Gtk.Label(
                        label=str(achievement[f"description_{self.language}"]),
                        wrap=True,
                        justify=Gtk.Justification.CENTER,
                        max_width_chars=24,
                        css_classes=["muted", "caption", "achievement-description"],
                    )
                )
                progress = min(int(achievement["progress"]), int(achievement["target"]))
                level.append(
                    Gtk.ProgressBar(
                        fraction=min(1.0, progress / max(1, int(achievement["target"]))),
                        css_classes=["achievement-progress"],
                    )
                )
                if is_unlocked:
                    status = (
                        f"Unlocked {datetime.fromtimestamp(float(unlocked_at)):%d.%m.%Y}"
                        if self.language == "en"
                        else f"Открыто {datetime.fromtimestamp(float(unlocked_at)):%d.%m.%Y}"
                    )
                else:
                    status = f"{progress} / {int(achievement['target'])}"
                level.append(Gtk.Label(label=status, css_classes=["achievement-status"]))
                levels.append(level)
            series_card.append(levels_frame)
            self.achievement_series_box.append(series_card)

    def _build_analytics(self) -> Gtk.Widget:
        scroller, content = self._page()
        content.append(
            self._heading("Экранное время", "Локальная статистика: ничего не отправляется в интернет.")
        )
        chart_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["card"])
        chart_card.append(Gtk.Label(label="Последние 7 дней", xalign=0, css_classes=["section-title"]))
        self.chart = WeekChart(self.app.db, self.language)
        chart_card.append(self.chart)
        content.append(chart_card)
        day_card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["card", "day-chart-card"]
        )
        day_head = self._stack_when_compact(Gtk.Box(spacing=10))
        day_head.append(
            Gtk.Label(label="Активность за день", xalign=0, hexpand=True, css_classes=["section-title"])
        )
        self.previous_day_button = Gtk.Button(
            label="‹ Previous" if self.language == "en" else "‹ Назад", css_classes=["day-nav-button"]
        )
        self.previous_day_button.connect("clicked", self._shift_analytics_day, -1)
        self.day_chart_date = Gtk.Label(css_classes=["day-chart-date"])
        date_content = Gtk.Box(spacing=6)
        date_content.append(Gtk.Image.new_from_icon_name("x-office-calendar-symbolic"))
        date_content.append(self.day_chart_date)
        date_content.append(Gtk.Image.new_from_icon_name("pan-down-symbolic"))
        self.day_date_button = Gtk.MenuButton(child=date_content, css_classes=["day-date-button"])
        self.day_calendar_popover = Gtk.Popover()
        self.day_calendar_popover.set_position(Gtk.PositionType.BOTTOM)
        self.day_calendar_popover.set_halign(Gtk.Align.CENTER)
        self.day_calendar = DateRangeCalendar(
            self.language,
            self.analytics_day,
            self.analytics_day,
            self.app.db.earliest_usage_day(),
            datetime.now().date(),
            self._calendar_day_selected,
            range_selection=False,
        )
        self.day_calendar_popover.set_child(self.day_calendar)
        self.day_date_button.set_popover(self.day_calendar_popover)
        self.next_day_button = Gtk.Button(
            label="Next ›" if self.language == "en" else "Вперёд ›", css_classes=["day-nav-button"]
        )
        self.next_day_button.connect("clicked", self._shift_analytics_day, 1)
        day_head.append(self.previous_day_button)
        day_head.append(self.day_date_button)
        day_head.append(self.next_day_button)
        day_card.append(day_head)
        day_card.append(
            Gtk.Label(
                label="Каждый столбец — один час. Цвет показывает приложение, число сверху — общее активное время. График можно прокручивать по горизонтали.",
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        self.day_chart = DayActivityChart(self.app.db, self.analytics_day.isoformat(), self.language)
        day_chart_scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vscrollbar_policy=Gtk.PolicyType.NEVER,
            css_classes=["day-chart-scroll"],
        )
        day_chart_scroll.set_overlay_scrolling(True)
        day_chart_scroll.set_child(self.day_chart)
        day_card.append(day_chart_scroll)
        content.append(day_card)
        self._update_day_chart_header()
        apps_card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8, css_classes=["card", "apps-card"]
        )
        apps_card.append(Gtk.Label(label="Приложения", xalign=0, css_classes=["section-title"]))
        apps_card.append(
            Gtk.Label(
                label="Нажмите на глаз, чтобы убрать приложение из недельного и дневного графиков.",
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        self.apps_list = Gtk.ListBox(css_classes=["boxed-list"])
        self.apps_list.set_selection_mode(Gtk.SelectionMode.NONE)
        apps_card.append(self.apps_list)
        content.append(apps_card)

        exercise_card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12, css_classes=["card", "exercise-card"]
        )
        exercise_card.append(Gtk.Label(label="Упражнения за 7 дней", xalign=0, css_classes=["section-title"]))
        exercise_metrics = self._stack_when_compact(Gtk.Box(spacing=8, homogeneous=True))
        self.exercise_time_value = Gtk.Label(xalign=0, css_classes=["exercise-value"])
        self.exercise_done_value = Gtk.Label(xalign=0, css_classes=["exercise-value"])
        self.exercise_snoozed_value = Gtk.Label(xalign=0, css_classes=["exercise-value"])
        self.exercise_rate_value = Gtk.Label(xalign=0, css_classes=["exercise-value"])
        for title, value in (
            ("В упражнениях", self.exercise_time_value),
            ("Завершено", self.exercise_done_value),
            ("Отложено", self.exercise_snoozed_value),
            ("Без откладывания", self.exercise_rate_value),
        ):
            metric = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, css_classes=["exercise-metric"])
            metric.append(Gtk.Label(label=title, xalign=0, css_classes=["muted", "caption"]))
            metric.append(value)
            exercise_metrics.append(metric)
        exercise_card.append(exercise_metrics)
        self.exercise_list = Gtk.FlowBox(css_classes=["exercise-flow"])
        self.exercise_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.exercise_list.set_min_children_per_line(1)
        self.exercise_list.set_max_children_per_line(2)
        self.exercise_list.set_column_spacing(8)
        self.exercise_list.set_row_spacing(8)
        self.exercise_list.set_homogeneous(True)
        exercise_card.append(self.exercise_list)
        content.append(exercise_card)

        wellness_card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["card", "wellness-history-card"]
        )
        wellness_head = self._stack_when_compact(Gtk.Box(spacing=10))
        wellness_head.append(
            Gtk.Label(label="Самочувствие", xalign=0, hexpand=True, css_classes=["section-title"])
        )
        self.wellness_previous_day_button = Gtk.Button(
            label="‹ Previous period" if self.language == "en" else "‹ Прошлый период",
            css_classes=["day-nav-button"],
        )
        self.wellness_previous_day_button.connect("clicked", self._shift_wellness_day, -1)
        self.wellness_day_date = Gtk.Label(css_classes=["day-chart-date"])
        wellness_date_content = Gtk.Box(spacing=6)
        wellness_date_content.append(Gtk.Image.new_from_icon_name("x-office-calendar-symbolic"))
        wellness_date_content.append(self.wellness_day_date)
        wellness_date_content.append(Gtk.Image.new_from_icon_name("pan-down-symbolic"))
        self.wellness_date_button = Gtk.MenuButton(
            child=wellness_date_content, css_classes=["day-date-button"]
        )
        self.wellness_popover = Gtk.Popover()
        self.wellness_popover.set_position(Gtk.PositionType.BOTTOM)
        self.wellness_popover.set_halign(Gtk.Align.CENTER)
        self.wellness_calendar = DateRangeCalendar(
            self.language,
            self.wellness_range_start,
            self.wellness_range_end,
            self.app.db.earliest_usage_day(),
            datetime.now().date(),
            self._select_wellness_range,
        )
        self.wellness_popover.set_child(self.wellness_calendar)
        self.wellness_date_button.set_popover(self.wellness_popover)
        self.wellness_next_day_button = Gtk.Button(
            label="Next period ›" if self.language == "en" else "Следующий период ›",
            css_classes=["day-nav-button"],
        )
        self.wellness_next_day_button.connect("clicked", self._shift_wellness_day, 1)
        wellness_head.append(self.wellness_previous_day_button)
        wellness_head.append(self.wellness_date_button)
        wellness_head.append(self.wellness_next_day_button)
        wellness_card.append(wellness_head)
        self.wellness_stamp = Gtk.Label(xalign=0, wrap=True, css_classes=["muted", "caption"])
        wellness_card.append(self.wellness_stamp)
        symptom_grid = Gtk.Grid(column_spacing=8, row_spacing=8, column_homogeneous=True)
        self.wellness_bars: dict[str, Gtk.LevelBar] = {}
        self.wellness_score_labels: dict[str, Gtk.Label] = {}
        for index, (key, title) in enumerate(
            (
                ("headache", "Головная боль"),
                ("eyes", "Усталость глаз"),
                ("neck", "Шея и плечи"),
                ("back", "Поясница"),
            )
        ):
            metric = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7, css_classes=["symptom-metric"])
            head = Gtk.Box(spacing=8)
            head.append(Gtk.Label(label=title, xalign=0, hexpand=True, css_classes=["symptom-title"]))
            score = Gtk.Label(label="—", css_classes=["symptom-score"])
            head.append(score)
            metric.append(head)
            bar = Gtk.LevelBar(
                min_value=0, max_value=10, value=0, css_classes=["symptom-bar", f"symptom-{key}"]
            )
            metric.append(bar)
            symptom_grid.attach(metric, index % 2, index // 2, 1, 1)
            self.wellness_bars[key] = bar
            self.wellness_score_labels[key] = score
        wellness_card.append(symptom_grid)

        wellness_summary = self._stack_when_compact(Gtk.Box(spacing=8, homogeneous=True))
        self.wellness_screen_value = Gtk.Label(xalign=0, css_classes=["wellness-summary-value"])
        self.wellness_breaks_value = Gtk.Label(xalign=0, css_classes=["wellness-summary-value"])
        self.wellness_exercise_value = Gtk.Label(xalign=0, css_classes=["wellness-summary-value"])
        for title, value in (
            ("Экранное время", self.wellness_screen_value),
            ("Паузы", self.wellness_breaks_value),
            ("В упражнениях", self.wellness_exercise_value),
        ):
            metric = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL, spacing=2, css_classes=["wellness-summary"]
            )
            metric.append(Gtk.Label(label=title, xalign=0, css_classes=["muted", "caption"]))
            metric.append(value)
            wellness_summary.append(metric)
        wellness_card.append(wellness_summary)
        self.wellness_insight = Gtk.Label(xalign=0, wrap=True, css_classes=["wellness-insight", "caption"])
        wellness_card.append(self.wellness_insight)
        content.append(wellness_card)
        self._update_day_chart_header()
        self._update_wellness_header()
        return scroller

    def _save_wellness(self, _button: Gtk.Button) -> None:
        values = {key: int(scale.get_value()) for key, scale in self.wellness_scales.items()}
        saved_at = time.time()
        self.app.db.save_wellness(**values, now=saved_at)
        self.app.scheduler.mark_wellness_answered()
        self.app.withdraw_notification("wellness-checkin")
        self.wellness_status.set_text(self._wellness_saved_text(saved_at))
        self.refresh(rebuild_lists=True)

    def _wellness_saved_text(self, timestamp: float) -> str:
        moment = datetime.fromtimestamp(timestamp)
        if self.language == "en":
            months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
            return f"Saved · {months[moment.month - 1]} {moment.day}, {moment.year} at {moment:%H:%M}"
        return f"Сохранено · {moment:%d.%m.%Y}, {moment:%H:%M}"

    def _chart_categories(self) -> tuple[list[dict[str, Any]], list[sqlite3.Row]]:
        apps = self.app.db.top_apps(days=7, limit=1000)
        shown = apps if len(apps) <= 6 else apps[:5]
        categories = [
            {
                "app_id": str(item["app_id"]),
                "name": str(item["app_name"]),
                "seconds": float(item["seconds"]),
                "color": CHART_COLORS[index],
            }
            for index, item in enumerate(shown)
        ]
        if len(apps) > 6:
            categories.append(
                {
                    "app_id": "__other__",
                    "name": "Other applications" if self.language == "en" else "Другие приложения",
                    "seconds": sum(float(item["seconds"]) for item in apps[5:]),
                    "color": CHART_COLORS[5],
                }
            )
        return categories, apps

    def _exercise_result_row(
        self, kind: str, done_count: int, snoozed_count: int, seconds: float
    ) -> Gtk.Widget:
        meta = localized_reminder_meta(self.language, kind, REMINDER_META[kind])
        content = Gtk.Box(spacing=11, hexpand=True, css_classes=["exercise-result-card"])
        content.append(activity_icon(kind, 22, "exercise-icon-shell"))
        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True)
        copy.append(Gtk.Label(label=str(meta["title"]), xalign=0, css_classes=["exercise-row-title"]))
        stats = Gtk.Box(spacing=7, css_classes=["exercise-stats"])
        labels = (
            ("Completed" if self.language == "en" else "Выполнено", str(done_count), "done"),
            ("Time" if self.language == "en" else "Время", format_duration(seconds, self.language), "time"),
            ("Postponed" if self.language == "en" else "Отложено", str(snoozed_count), "postponed"),
        )
        for label_text, value_text, style in labels:
            badge = Gtk.Box(spacing=5, css_classes=["exercise-stat", f"exercise-stat-{style}"])
            badge.append(Gtk.Label(label=label_text, css_classes=["exercise-stat-label"]))
            badge.append(Gtk.Label(label=value_text, css_classes=["exercise-stat-value"]))
            stats.append(badge)
        copy.append(stats)
        content.append(copy)
        return content

    def _analytics_visibility_changed(self, button: Gtk.ToggleButton, app_id: str) -> None:
        if button.get_active():
            self.analytics_hidden_apps.discard(app_id)
            button.set_icon_name("view-reveal-symbolic")
        else:
            self.analytics_hidden_apps.add(app_id)
            button.set_icon_name("view-conceal-symbolic")
        self.app.config.data["analytics_hidden_apps"] = sorted(self.analytics_hidden_apps)
        self.app.config.save()
        row = button.get_ancestor(Adw.ActionRow)
        if row:
            row.set_opacity(1.0 if button.get_active() else 0.55)
        categories, _apps = self._chart_categories()
        self.chart.set_categories(categories, self.analytics_hidden_apps)
        self.day_chart.set_categories(categories, self.analytics_hidden_apps)

    def _shift_analytics_day(self, _button: Gtk.Button, offset: int) -> None:
        target = self.analytics_day + timedelta(days=offset)
        today = datetime.now().date()
        if target > today or target < self.app.db.earliest_usage_day():
            return
        self._select_analytics_day(target)

    def _select_analytics_day(self, target: date) -> None:
        self.analytics_day = target
        self.day_chart.set_day(target.isoformat())
        self.day_calendar.set_range(target, target, show_end_month=True)
        self._update_day_chart_header()
        self.refresh(rebuild_lists=True)

    def _calendar_day_selected(self, target: date, _unused_end: date) -> None:
        if target == self.analytics_day:
            self.day_date_button.popdown()
            return
        self._select_analytics_day(target)
        self.day_date_button.popdown()

    def _shift_wellness_day(self, _button: Gtk.Button, offset: int) -> None:
        span = (self.wellness_range_end - self.wellness_range_start).days + 1
        delta = timedelta(days=span * offset)
        start = self.wellness_range_start + delta
        end = self.wellness_range_end + delta
        earliest = self.app.db.earliest_usage_day()
        today = datetime.now().date()
        if start < earliest:
            start = earliest
            end = min(today, start + timedelta(days=span - 1))
        if end > today:
            end = today
            start = max(earliest, end - timedelta(days=span - 1))
        if (start, end) == (self.wellness_range_start, self.wellness_range_end):
            return
        self._select_wellness_range(start, end)

    def _select_wellness_range(self, start: date, end: date) -> None:
        earliest = self.app.db.earliest_usage_day()
        today = datetime.now().date()
        self.wellness_range_start = max(earliest, min(start, end))
        self.wellness_range_end = min(today, max(start, end))
        self.wellness_calendar.set_range(
            self.wellness_range_start, self.wellness_range_end, show_end_month=True
        )
        self.wellness_date_button.popdown()
        self._update_wellness_header()
        self.refresh(rebuild_lists=True)

    def _update_day_chart_header(self) -> None:
        today = datetime.now().date()
        if self.language == "en":
            months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
            prefix = "Today · " if self.analytics_day == today else ""
            label = f"{prefix}{months[self.analytics_day.month - 1]} {self.analytics_day.day}"
        else:
            prefix = "Сегодня · " if self.analytics_day == today else ""
            label = f"{prefix}{self.analytics_day:%d.%m}"
        self.day_chart_date.set_text(label)
        self.previous_day_button.set_sensitive(self.analytics_day > self.app.db.earliest_usage_day())
        self.next_day_button.set_sensitive(self.analytics_day < today)

    def _update_wellness_header(self) -> None:
        if not hasattr(self, "wellness_day_date"):
            return
        start = self.wellness_range_start
        end = self.wellness_range_end
        today = datetime.now().date()
        if self.language == "en":
            months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
            start_text = f"{months[start.month - 1]} {start.day}"
            end_text = f"{months[end.month - 1]} {end.day}, {end.year}"
            label = f"{start_text} – {end_text}" if start != end else end_text
        else:
            start_text = start.strftime("%d.%m")
            end_text = end.strftime("%d.%m.%Y")
            label = f"{start_text} — {end_text}" if start != end else end_text
        self.wellness_day_date.set_text(label)
        self.wellness_previous_day_button.set_sensitive(start > self.app.db.earliest_usage_day())
        self.wellness_next_day_button.set_sensitive(end < today)

    def _build_settings(self) -> Gtk.Widget:
        scroller, content = self._page()
        language_card = Gtk.Box(spacing=14, css_classes=["card", "language-card"])
        language_card.append(symbolic_icon("preferences-desktop-locale-symbolic", css_class="language-icon"))
        language_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        language_copy.append(
            Gtk.Label(
                label="Language" if self.language == "en" else "Язык",
                xalign=0,
                css_classes=["settings-title"],
            )
        )
        language_copy.append(
            Gtk.Label(
                label="Interface and exercise instructions"
                if self.language == "en"
                else "Интерфейс и инструкции упражнений",
                xalign=0,
                css_classes=["muted", "caption"],
            )
        )
        language_card.append(language_copy)
        language_picker = Gtk.DropDown.new_from_strings(["English", "Русский"])
        language_picker.add_css_class("language-picker")
        language_picker.set_selected(0 if self.language == "en" else 1)
        language_picker.set_valign(Gtk.Align.CENTER)
        language_picker.connect("notify::selected", self._language_changed)
        language_card.append(language_picker)
        settings_hero = Gtk.Box(spacing=22, css_classes=["settings-hero"])
        settings_hero_icon = Gtk.Image.new_from_icon_name("preferences-system-symbolic")
        settings_hero_icon.set_pixel_size(34)
        settings_hero_icon.add_css_class("settings-hero-icon")
        settings_hero_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        settings_hero_copy.append(
            Gtk.Label(label="Ваш режим — ваши правила", xalign=0, css_classes=["settings-hero-title"])
        )
        settings_hero_copy.append(
            Gtk.Label(
                label="Базовый профиль уже настроен. Меняйте только то, что действительно помогает.",
                xalign=0,
                wrap=True,
                css_classes=["settings-hero-copy"],
            )
        )
        settings_hero.append(settings_hero_icon)
        settings_hero.append(settings_hero_copy)
        content.append(settings_hero)
        content.append(language_card)
        content.append(self._theme_settings_card())
        content.append(self._palette_settings_card())
        content.append(self._snooze_settings_card())
        content.append(self._wellness_reminder_settings_card())

        labels = {
            "eyes": "Отдых для глаз",
            "general": "Общая разминка",
            "neck": "Шея и плечи",
            "drops": "Капли для глаз",
            "back": "Поясница и таз",
            "wrists": "Кисти и предплечья",
            "breathing": "Спокойное дыхание",
            "water": "Проверить жажду",
        }
        subtitles = {
            "eyes": "Чередует даль, смену фокуса и отдых",
            "general": "Двенадцать видов пауз по очереди",
            "neck": "Шесть мягких комплексов по очереди",
            "drops": "Настройте строго по своей схеме",
            "back": "Пять комплексов; выключено по умолчанию",
            "wrists": "Пять комплексов; выключено по умолчанию",
            "breathing": "Пять вариантов; выключено по умолчанию",
            "water": "Без навязанной нормы жидкости",
        }
        for section_title, kinds, section_hint in (
            (
                "Основной режим",
                ("eyes", "general", "neck", "drops"),
                "Рекомендованный профиль — всё уже включено",
            ),
            (
                "Дополнительно",
                ("back", "wrists", "breathing", "water"),
                "Эти активности не включаются без вашего решения",
            ),
        ):
            section_head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            section_head.append(Gtk.Label(label=section_title, xalign=0, css_classes=["section-title"]))
            section_head.append(Gtk.Label(label=section_hint, xalign=0, css_classes=["muted", "caption"]))
            content.append(section_head)
            grid = self._responsive_flow("settings-flow")
            for kind in kinds:
                grid.append(self._activity_settings_card(kind, labels[kind], subtitles[kind]))
            content.append(grid)

        content.append(Gtk.Label(label="Поведение", xalign=0, css_classes=["section-title"]))
        behavior_grid = self._responsive_flow("settings-flow", spacing=14)
        behavior_grid.add_css_class("behavior-flow")
        behavior_grid.set_homogeneous(False)
        fullscreen_card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=14, css_classes=["settings-card"]
        )
        fullscreen_head = Gtk.Box(spacing=12)
        fullscreen_icon = symbolic_icon("view-fullscreen-symbolic")
        fullscreen_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        fullscreen_copy.append(Gtk.Label(label="Полный экран", xalign=0, css_classes=["settings-title"]))
        fullscreen_copy.append(
            Gtk.Label(
                label="Не беспокоить поверх видео и презентаций",
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        fullscreen = Gtk.Switch(
            active=bool(self.app.config.data.get("pause_on_fullscreen", False)), valign=Gtk.Align.CENTER
        )
        fullscreen.connect("notify::active", self._fullscreen_changed)
        fullscreen_head.append(fullscreen_icon)
        fullscreen_head.append(fullscreen_copy)
        fullscreen_head.append(fullscreen)
        fullscreen_card.append(fullscreen_head)

        idle_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14, css_classes=["settings-card"])
        idle_head = Gtk.Box(spacing=12)
        idle_head.append(symbolic_icon("alarm-symbolic"))
        idle_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        idle_copy.append(Gtk.Label(label="Бездействие", xalign=0, css_classes=["settings-title"]))
        idle_copy.append(
            Gtk.Label(
                label="Останавливает счётчик без активности, кроме полноэкранного просмотра",
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        idle_head.append(idle_copy)
        idle_card.append(idle_head)
        idle_stepper, _ = self._make_stepper(
            int(self.app.config.data["idle_threshold_seconds"]),
            30,
            600,
            15,
            lambda value: self._set_idle_value(value),
            lambda value: f"{value} {'sec' if self.language == 'en' else 'сек'}",
        )
        idle_card.append(idle_stepper)
        behavior_grid.append(fullscreen_card)
        behavior_grid.append(idle_card)

        share_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["settings-card"])
        share_head = Gtk.Box(spacing=12)
        share_head.append(symbolic_icon("video-display-symbolic"))
        share_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        share_copy.append(Gtk.Label(label="Демонстрация экрана", xalign=0, css_classes=["settings-title"]))
        share_copy.append(
            Gtk.Label(
                label="Не открывать напоминания на созвоне; статистика продолжит считаться",
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        share_head.append(share_copy)
        share_switch = Gtk.Switch(
            active=bool(self.app.config.data.get("pause_on_screen_share", True)),
            valign=Gtk.Align.CENTER,
        )

        def screen_share_changed(switch: Gtk.Switch, _pspec: Any) -> None:
            self.app.config.data["pause_on_screen_share"] = switch.get_active()
            self.app.config.save()

        share_switch.connect("notify::active", screen_share_changed)
        share_head.append(share_switch)
        share_card.append(share_head)
        behavior_grid.append(share_card)

        sound_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["settings-card"])
        sound_head = Gtk.Box(spacing=12)
        sound_head.append(symbolic_icon("audio-volume-high-symbolic"))
        sound_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        sound_copy.append(Gtk.Label(label="Звуковые подсказки", xalign=0, css_classes=["settings-title"]))
        sound_copy.append(
            Gtk.Label(
                label="Сигнал в начале, при смене этапа и в конце упражнения",
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        sound_head.append(sound_copy)
        sound_switch = Gtk.Switch(
            active=bool(self.app.config.data.get("guided_sound_enabled", True)),
            valign=Gtk.Align.CENTER,
        )
        sound_head.append(sound_switch)
        sound_card.append(sound_head)
        volume_row = Gtk.Box(spacing=9)
        volume_row.append(Gtk.Image.new_from_icon_name("audio-volume-low-symbolic"))
        volume = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, -30.0, 0.0, 1.0)
        volume.set_value(float(self.app.config.data.get("guided_sound_volume", -8.0)))
        volume.set_draw_value(False)
        volume.set_hexpand(True)
        volume_row.append(volume)
        volume_row.append(Gtk.Image.new_from_icon_name("audio-volume-high-symbolic"))
        test_sound = Gtk.Button(label="Проверить звук", css_classes=["test-button"], halign=Gtk.Align.END)

        def update_sound_controls(active: bool) -> None:
            volume.set_sensitive(active)
            test_sound.set_sensitive(active)

        def sound_enabled_changed(switch: Gtk.Switch, _pspec: Any) -> None:
            self.app.config.data["guided_sound_enabled"] = switch.get_active()
            self.app.config.save()
            update_sound_controls(switch.get_active())

        def sound_volume_changed(scale: Gtk.Scale) -> None:
            self.app.config.data["guided_sound_volume"] = round(scale.get_value(), 1)
            self.app.config.save()

        sound_switch.connect("notify::active", sound_enabled_changed)
        volume.connect("value-changed", sound_volume_changed)
        test_sound.connect("clicked", lambda _button: play_guidance_sound(self.app.config.data, "done"))
        update_sound_controls(sound_switch.get_active())
        sound_card.append(volume_row)
        sound_card.append(test_sound)
        behavior_grid.append(sound_card)

        content.append(behavior_grid)
        content.append(self._backup_settings_card())

        privacy = Gtk.Box(spacing=16, css_classes=["privacy-card"])
        privacy.append(symbolic_icon("security-high-symbolic", css_class="privacy-icon"))
        privacy_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True)
        privacy_copy.append(
            Gtk.Label(
                label="Все данные остаются на этом компьютере", xalign=0, css_classes=["settings-title"]
            )
        )
        privacy_copy.append(
            Gtk.Label(
                label="Сохраняются только название приложения, длительность и отметки о паузах. Снимков экрана нет.",
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        privacy.append(privacy_copy)
        content.append(privacy)
        return scroller

    def _theme_settings_card(self) -> Gtk.Widget:
        card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            css_classes=["settings-card", "theme-settings-card"],
        )
        head = Gtk.Box(spacing=12)
        head.append(symbolic_icon("applications-graphics-symbolic"))
        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        copy.append(Gtk.Label(label="Оформление", xalign=0, css_classes=["settings-title"]))
        copy.append(
            Gtk.Label(
                label="Выберите тему вручную или переключайте её по расписанию",
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        head.append(copy)
        mode_names = (
            ["Light", "Dark", "Automatic"]
            if self.language == "en"
            else ["Светлая", "Тёмная", "Автоматически"]
        )
        modes = ("light", "dark", "auto")
        current_mode = str(self.app.config.data.get("theme_mode", "light"))
        mode_picker = Gtk.DropDown.new_from_strings(mode_names)
        self.theme_mode_picker = mode_picker
        mode_picker.add_css_class("theme-picker")
        mode_picker.set_selected(modes.index(current_mode) if current_mode in modes else 0)
        mode_picker.set_valign(Gtk.Align.CENTER)
        head.append(mode_picker)
        card.append(head)

        schedule = self._stack_when_compact(
            Gtk.Box(spacing=10, homogeneous=True, css_classes=["theme-schedule"])
        )
        self._building_page_breakpoint.add_setter(schedule, "margin-start", 0)

        def make_time_picker(key: str, title: str) -> Gtk.Widget:
            saved = normalize_clock(
                self.app.config.data.get(key), "07:00" if key.endswith("light_time") else "21:00"
            )
            values = [f"{minute // 60:02d}:{minute % 60:02d}" for minute in range(0, 24 * 60, 15)]
            if saved not in values:
                values.append(saved)
                values.sort(key=lambda value: tuple(int(part) for part in value.split(":")))
            box = Gtk.Box(spacing=9, css_classes=["theme-time-control"])
            box.append(Gtk.Label(label=title, xalign=0, hexpand=True, css_classes=["caption"]))
            picker = Gtk.DropDown.new_from_strings(values)
            picker.add_css_class("theme-time-picker")
            picker.set_selected(values.index(saved))

            def changed(widget: Gtk.DropDown, _pspec: Any) -> None:
                self.app.config.data[key] = values[widget.get_selected()]
                self.app.config.save()
                if self.app.config.data.get("theme_mode") == "auto":
                    self.app.apply_color_scheme()

            picker.connect("notify::selected", changed)
            box.append(picker)
            return box

        schedule.append(make_time_picker("theme_light_time", "Светлая тема с"))
        schedule.append(make_time_picker("theme_dark_time", "Тёмная тема с"))
        schedule.set_sensitive(current_mode == "auto")
        self.theme_schedule = schedule
        card.append(schedule)

        def mode_changed(widget: Gtk.DropDown, _pspec: Any) -> None:
            if self._syncing_theme_control:
                return
            mode = modes[widget.get_selected()]
            self.app.config.data["theme_mode"] = mode
            if mode != "auto":
                self.app.config.data["dark_mode"] = mode == "dark"
            self.app.config.save()
            schedule.set_sensitive(mode == "auto")
            self.app.apply_color_scheme()

        mode_picker.connect("notify::selected", mode_changed)

        return card

    def _palette_settings_card(self) -> Gtk.Widget:
        palettes = ("teal", "burgundy", "gray")
        names = ("Teal", "Burgundy", "Gray") if self.language == "en" else ("Бирюзовая", "Бордовая", "Серая")
        current = normalize_color_theme(self.app.config.data.get("color_theme"))
        card = Gtk.Box(
            spacing=14,
            css_classes=["card", "language-card", "palette-settings-card"],
        )
        card.append(PaletteEmblem(current))
        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        copy.append(Gtk.Label(label="Цветовая тема", xalign=0, css_classes=["settings-title"]))
        copy.append(
            Gtk.Label(
                label="Один акцент для светлого и тёмного оформления",
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        card.append(copy)

        model = Gtk.StringList.new(list(names))
        picker = Gtk.DropDown(model=model)
        picker.add_css_class("palette-picker")
        picker.set_selected(palettes.index(current))
        picker.set_valign(Gtk.Align.CENTER)

        def palette_factory() -> Gtk.SignalListItemFactory:
            factory = Gtk.SignalListItemFactory()

            def setup(_factory: Gtk.SignalListItemFactory, item: Gtk.ListItem) -> None:
                row = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
                dot = ColorSwatch(COLOR_PALETTES["teal"]["accent"], 11)
                dot.add_css_class("palette-option-dot")
                row.append(dot)
                row.append(Gtk.Label(xalign=0))
                item.set_child(row)

            def bind(_factory: Gtk.SignalListItemFactory, item: Gtk.ListItem) -> None:
                position = max(0, min(len(palettes) - 1, item.get_position()))
                row = item.get_child()
                dot = row.get_first_child()
                label = dot.get_next_sibling()
                dot.set_color(COLOR_PALETTES[palettes[position]]["accent"])
                label.set_text(names[position])

            factory.connect("setup", setup)
            factory.connect("bind", bind)
            return factory

        picker.set_factory(palette_factory())
        picker.set_list_factory(palette_factory())

        def palette_changed(widget: Gtk.DropDown, _pspec: Any) -> None:
            palette = palettes[widget.get_selected()]
            if palette == self.app.config.data.get("color_theme"):
                return
            self.app.config.data["color_theme"] = palette
            self.app.config.save()
            self.app.apply_palette()

        picker.connect("notify::selected", palette_changed)
        card.append(picker)
        return card

    def _language_changed(self, picker: Gtk.DropDown, _pspec: Any) -> None:
        language = "en" if picker.get_selected() == 0 else "ru"
        if language == self.language:
            return
        self.app.set_language(language, "settings")

    def _backup_settings_card(self) -> Gtk.Widget:
        card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["settings-card", "backup-card"]
        )
        head = Gtk.Box(spacing=12)
        head.append(symbolic_icon("document-save-symbolic"))
        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        copy.append(Gtk.Label(label="Перенос данных", xalign=0, css_classes=["settings-title"]))
        copy.append(
            Gtk.Label(
                label="Экспортирует аналитику, достижения, курсы и все настройки. Импорт полностью заменяет текущие данные.",
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        head.append(copy)
        actions = Gtk.Box(spacing=8, valign=Gtk.Align.CENTER)
        export_button = Gtk.Button(label="Экспортировать", css_classes=["data-button", "data-primary"])
        import_button = Gtk.Button(label="Импортировать", css_classes=["data-button"])
        export_button.connect("clicked", self._export_backup)
        import_button.connect("clicked", self._choose_backup)
        actions.append(import_button)
        actions.append(export_button)
        head.append(actions)
        card.append(head)
        self.backup_status = Gtk.Label(
            xalign=0, wrap=True, visible=False, css_classes=["backup-status", "caption"]
        )
        card.append(self.backup_status)
        return card

    def _backup_payload(self) -> dict[str, Any]:
        return {
            "format": "zdorovo-backup",
            "version": 1,
            "exported_at": time.time(),
            "settings": self.app.config.data,
            "analytics": self.app.db.backup_tables(),
        }

    def _export_backup(self, _button: Gtk.Button) -> None:
        title = "Export Zdorovo data" if self.language == "en" else "Экспорт данных Здорово"
        chooser = Gtk.FileChooserNative.new(
            title,
            self,
            Gtk.FileChooserAction.SAVE,
            "Export" if self.language == "en" else "Экспортировать",
            "Cancel" if self.language == "en" else "Отмена",
        )
        chooser.set_current_name(f"zdorovo-backup-{datetime.now():%Y-%m-%d}.json")
        chooser.connect("response", self._export_chosen)
        self._backup_chooser = chooser
        chooser.show()

    def _export_chosen(self, chooser: Gtk.FileChooserNative, response: int) -> None:
        if response == Gtk.ResponseType.ACCEPT:
            file = chooser.get_file()
            path = Path(file.get_path()) if file and file.get_path() else None
            if path:
                try:
                    if path.suffix.lower() != ".json":
                        path = path.with_suffix(".json")
                    temporary = path.with_suffix(path.suffix + ".tmp")
                    temporary.write_text(
                        json.dumps(self._backup_payload(), ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    temporary.replace(path)
                    self._show_backup_status(
                        (f"Saved: {path.name}" if self.language == "en" else f"Сохранено: {path.name}"), False
                    )
                except (OSError, TypeError, ValueError) as error:
                    self._show_backup_status(
                        (
                            f"Export failed: {error}"
                            if self.language == "en"
                            else f"Не удалось экспортировать: {error}"
                        ),
                        True,
                    )
        chooser.destroy()
        self._backup_chooser = None

    def _choose_backup(self, _button: Gtk.Button) -> None:
        title = "Import Zdorovo data" if self.language == "en" else "Импорт данных Здорово"
        chooser = Gtk.FileChooserNative.new(
            title,
            self,
            Gtk.FileChooserAction.OPEN,
            "Choose" if self.language == "en" else "Выбрать",
            "Cancel" if self.language == "en" else "Отмена",
        )
        file_filter = Gtk.FileFilter()
        file_filter.set_name("Zdorovo backup (*.json)")
        file_filter.add_pattern("*.json")
        chooser.add_filter(file_filter)
        chooser.connect("response", self._import_chosen)
        self._backup_chooser = chooser
        chooser.show()

    def _import_chosen(self, chooser: Gtk.FileChooserNative, response: int) -> None:
        path: Path | None = None
        if response == Gtk.ResponseType.ACCEPT:
            file = chooser.get_file()
            path = Path(file.get_path()) if file and file.get_path() else None
        chooser.destroy()
        self._backup_chooser = None
        if not path:
            return
        heading = "Replace current data?" if self.language == "en" else "Заменить текущие данные?"
        body = (
            "Settings, analytics, achievements and training courses will be restored from the selected backup. This cannot be undone."
            if self.language == "en"
            else "Настройки, аналитика, достижения и курсы будут восстановлены из выбранной копии. Отменить это действие нельзя."
        )
        dialog = Adw.MessageDialog.new(self, heading, body)
        dialog.add_response("cancel", "Cancel" if self.language == "en" else "Отмена")
        dialog.add_response("import", "Import" if self.language == "en" else "Импортировать")
        dialog.set_response_appearance("import", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect(
            "response", lambda _dialog, answer: self._restore_backup(path) if answer == "import" else None
        )
        dialog.present()

    def _restore_backup(self, path: Path) -> None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("format") != "zdorovo-backup"
                or payload.get("version") != 1
            ):
                raise ValueError("unsupported backup format")
            settings = payload.get("settings")
            analytics = payload.get("analytics")
            if not isinstance(settings, dict) or not isinstance(analytics, dict):
                raise ValueError("incomplete backup")
            restored_config = deep_merge(DEFAULT_CONFIG, settings)
            restored_config["manual_pause"] = False
            restored_config["snooze_minutes"] = max(1, min(20, int(restored_config.get("snooze_minutes", 5))))
            if restored_config.get("language") not in ("en", "ru"):
                restored_config["language"] = "en"
            if settings.get("theme_mode") not in ("light", "dark", "auto"):
                restored_config["theme_mode"] = "dark" if bool(settings.get("dark_mode", False)) else "light"
            restored_config["theme_light_time"] = normalize_clock(
                restored_config.get("theme_light_time"), "07:00"
            )
            restored_config["theme_dark_time"] = normalize_clock(
                restored_config.get("theme_dark_time"), "21:00"
            )
            restored_config["color_theme"] = normalize_color_theme(restored_config.get("color_theme"))
            if restored_config.get("training_fitness_level") not in FITNESS_LEVELS:
                restored_config["training_fitness_level"] = "beginner"
            training_days = max(2, min(5, int(restored_config.get("training_days_per_week", 3))))
            try:
                training_weekdays = normalize_weekdays(
                    restored_config.get("training_weekdays"),
                    training_days,
                )
            except ValueError:
                training_weekdays = normalize_weekdays(None, training_days)
            restored_config["training_weekdays"] = list(training_weekdays)
            restored_config["training_days_per_week"] = len(training_weekdays)
            restored_config["training_reminders_enabled"] = bool(
                restored_config.get("training_reminders_enabled", True)
            )
            reminder_time = restored_config.get("training_reminder_time")
            restored_config["training_reminder_time"] = (
                normalize_clock(reminder_time, "18:00")
                if isinstance(reminder_time, str) and reminder_time.strip()
                else None
            )
            self.app.db.restore_tables(analytics)
            self.app.config.data = restored_config
            self.app.config.save()
            set_active_color_theme(str(restored_config["color_theme"]))
            self.app._load_css()
            self.app.apply_color_scheme()
            self.app.rebuild_window("settings")
        except (OSError, ValueError, TypeError, sqlite3.Error) as error:
            self._show_backup_status(
                (
                    f"Import failed: {error}"
                    if self.language == "en"
                    else f"Не удалось импортировать: {error}"
                ),
                True,
            )

    def _show_backup_status(self, message: str, error: bool) -> None:
        self.backup_status.set_text(message)
        self.backup_status.set_visible(True)
        if error:
            self.backup_status.add_css_class("error")
        else:
            self.backup_status.remove_css_class("error")

    def _snooze_settings_card(self) -> Gtk.Widget:
        card = Gtk.Box(spacing=12, css_classes=["settings-card", "snooze-settings-card"])
        card.append(symbolic_icon("alarm-symbolic"))
        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        copy.append(Gtk.Label(label="Напомнить позже", xalign=0, css_classes=["settings-title"]))
        copy.append(
            Gtk.Label(
                label="Через сколько минут снова показать отложенное напоминание",
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        card.append(copy)
        stepper, _ = self._make_stepper(
            int(self.app.config.data.get("snooze_minutes", 5)),
            1,
            20,
            1,
            self._set_snooze_value,
            lambda value: f"{value} min" if self.language == "en" else f"{value} мин",
        )
        stepper.set_size_request(210, -1)
        stepper.set_valign(Gtk.Align.CENTER)
        card.append(stepper)
        return card

    def _wellness_reminder_settings_card(self) -> Gtk.Widget:
        card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
            css_classes=["settings-card", "wellness-reminder-settings-card"],
        )
        head = Gtk.Box(spacing=12)
        head.append(symbolic_icon("user-available-symbolic"))
        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        copy.append(
            Gtk.Label(
                label="Ежедневная оценка самочувствия",
                xalign=0,
                css_classes=["settings-title"],
            )
        )
        copy.append(
            Gtk.Label(
                label="Показывать карточку самочувствия на главном экране",
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        head.append(copy)
        enabled = Gtk.Switch(
            active=bool(self.app.config.data.get("wellness_checkin_enabled", True)),
            valign=Gtk.Align.CENTER,
        )
        head.append(enabled)
        card.append(head)

        reminder_row = Gtk.Box(spacing=10, css_classes=["settings-subrow"])
        reminder_row.append(symbolic_icon("alarm-symbolic", 17, "settings-subrow-icon"))
        reminder_copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        reminder_copy.append(
            Gtk.Label(label="Напоминания об оценке", xalign=0, css_classes=["settings-title"])
        )
        reminder_copy.append(
            Gtk.Label(
                label="До трёх напоминаний в день; после ответа больше не беспокоит",
                xalign=0,
                wrap=True,
                css_classes=["muted", "caption"],
            )
        )
        reminder_row.append(reminder_copy)
        reminders_enabled = Gtk.Switch(
            active=bool(self.app.config.data.get("wellness_reminders_enabled", True)),
            valign=Gtk.Align.CENTER,
        )
        reminder_row.append(reminders_enabled)
        reminder_row.set_sensitive(enabled.get_active())
        card.append(reminder_row)

        def wellness_checkin_changed(switch: Gtk.Switch, _pspec: Any) -> None:
            active = switch.get_active()
            self.app.config.data["wellness_checkin_enabled"] = active
            self.app.config.save()
            reminder_row.set_sensitive(active)
            self.app.scheduler.state["wellness_active_seconds"] = 0.0
            self.app.scheduler.state["wellness_prompt_count"] = 0
            self.app.scheduler._save_state()
            if not active:
                self.app.withdraw_notification("wellness-checkin")
            self.refresh()

        def wellness_reminders_changed(switch: Gtk.Switch, _pspec: Any) -> None:
            self.app.config.data["wellness_reminders_enabled"] = switch.get_active()
            self.app.config.save()
            if not switch.get_active():
                self.app.withdraw_notification("wellness-checkin")

        enabled.connect("notify::active", wellness_checkin_changed)
        reminders_enabled.connect("notify::active", wellness_reminders_changed)
        return card

    def _activity_settings_card(self, kind: str, title: str, subtitle: str) -> Gtk.Widget:
        options = self.app.config.reminder(kind)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["settings-card"])
        head = Gtk.Box(spacing=12)
        head.append(activity_icon(kind, 24, "settings-icon"))
        copy = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        copy.append(Gtk.Label(label=title, xalign=0, wrap=True, css_classes=["settings-title"]))
        copy.append(Gtk.Label(label=subtitle, xalign=0, wrap=True, css_classes=["muted", "caption"]))
        head.append(copy)
        enabled = Gtk.Switch(active=bool(options["enabled"]), valign=Gtk.Align.CENTER)
        head.append(enabled)
        card.append(head)

        if kind == "drops":
            value, minimum, maximum, step = int(options.get("times_per_day", 4)), 1, 8, 1
            formatter = (
                (lambda number: f"{number} times/day")
                if self.language == "en"
                else (lambda number: f"{number} раз/день")
            )
        else:
            value, minimum, maximum, step = (
                int(options["interval_minutes"]),
                5 if kind == "eyes" else 15,
                480,
                5,
            )
            formatter = (
                (lambda number: f"every {number} min")
                if self.language == "en"
                else (lambda number: f"каждые {number} мин")
            )
        stepper, controls = self._make_stepper(
            value,
            minimum,
            maximum,
            step,
            lambda number, k=kind: self._set_reminder_frequency(k, number),
            formatter,
        )
        card.append(stepper)

        if kind in CUSTOM_DURATION_LIMITS:
            duration_min, duration_max, duration_step = CUSTOM_DURATION_LIMITS[kind]
            duration = int(options.get("duration_seconds", REMINDER_META[kind].get("duration_seconds", 120)))
            duration_control, duration_buttons = self._make_stepper(
                duration,
                duration_min,
                duration_max,
                duration_step,
                lambda seconds, k=kind: self._set_reminder_duration(k, seconds),
                lambda seconds: (
                    ("duration " if self.language == "en" else "длительность ")
                    + format_precise_duration(seconds, self.language)
                ),
            )
            card.append(duration_control)
            controls.extend(duration_buttons)

        test = Gtk.Button(css_classes=["test-button"], halign=Gtk.Align.END)
        test_content = Gtk.Box(spacing=6)
        test_content.append(Gtk.Image.new_from_icon_name("media-playback-start-symbolic"))
        test_content.append(Gtk.Label(label="Проверить"))
        test.set_child(test_content)
        test.connect("clicked", lambda _button, k=kind: self.app.scheduler.trigger(k))
        card.append(Gtk.Box(vexpand=True))
        card.append(test)
        controls.append(test)

        def apply_visual(active: bool) -> None:
            for widget in controls:
                widget.set_sensitive(active)
            card.set_opacity(1.0 if active else 0.62)

        def update_state(switch: Gtk.Switch, _pspec: Any = None) -> None:
            active = switch.get_active()
            self.app.config.reminder(kind)["enabled"] = active
            self.app.config.save()
            apply_visual(active)
            self.refresh()

        enabled.connect("notify::active", update_state)
        apply_visual(enabled.get_active())
        return card

    def _make_stepper(
        self,
        initial: int,
        minimum: int,
        maximum: int,
        step: int,
        changed: Callable[[int], None],
        formatter: Callable[[int], str],
    ) -> tuple[Gtk.Widget, list[Gtk.Widget]]:
        value = {"current": initial}
        box = Gtk.Box(spacing=6, css_classes=["frequency-control"])
        minus = Gtk.Button(icon_name="list-remove-symbolic", css_classes=["step-button"])
        label = Gtk.Label(label=formatter(initial), hexpand=True, css_classes=["frequency-value"])
        plus = Gtk.Button(icon_name="list-add-symbolic", css_classes=["step-button"])

        def move(_button: Gtk.Button, direction: int) -> None:
            new_value = max(minimum, min(maximum, value["current"] + direction * step))
            if new_value == value["current"]:
                return
            value["current"] = new_value
            label.set_text(formatter(new_value))
            changed(new_value)

        minus.connect("clicked", move, -1)
        plus.connect("clicked", move, 1)
        box.append(minus)
        box.append(label)
        box.append(plus)
        return box, [minus, plus]

    def _set_reminder_frequency(self, kind: str, value: int) -> None:
        key = "times_per_day" if kind == "drops" else "interval_minutes"
        self.app.config.reminder(kind)[key] = value
        self.app.config.save()
        self.refresh()

    def _set_idle_value(self, value: int) -> None:
        self.app.config.data["idle_threshold_seconds"] = value
        self.app.config.save()

    def _set_snooze_value(self, value: int) -> None:
        self.app.config.data["snooze_minutes"] = max(1, min(20, int(value)))
        self.app.config.save()

    def _set_reminder_duration(self, kind: str, seconds: int) -> None:
        if kind not in CUSTOM_DURATION_LIMITS:
            return
        minimum, maximum, _step = CUSTOM_DURATION_LIMITS[kind]
        self.app.config.reminder(kind)["duration_seconds"] = max(minimum, min(maximum, int(seconds)))
        self.app.config.save()

    def _build_health(self) -> Gtk.Widget:
        scroller, content = self._page()
        content.append(
            self._heading(
                "Это важно",
                "Приложение помогает менять рабочие привычки, но не заменяет профессиональную консультацию.",
            )
        )
        warning = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, css_classes=["warning-card"])
        warning.append(
            Gtk.Label(label="Когда лучше обратиться за советом", xalign=0, css_classes=["section-title"])
        )
        warning.append(
            Gtk.Label(
                label="Повторяющиеся, необычные или усиливающиеся симптомы лучше обсуждать с квалифицированным врачом. Если внезапно возникли выраженная слабость, онемение, нарушение речи, зрения или координации — обращайтесь за экстренной помощью.",
                xalign=0,
                wrap=True,
                css_classes=["body-copy"],
            )
        )
        content.append(warning)
        for title, text in (
            (
                "Движение",
                "Выбирайте медленную комфортную амплитуду без рывков и давления. Индивидуальный комплекс лучше согласовать с врачом.",
            ),
            (
                "Самочувствие",
                "Если активность вызывает неприятные ощущения, остановитесь. Повторяющиеся симптомы лучше обсудить с врачом.",
            ),
            (
                "Глаза и средства ухода",
                "Перерывы помогают снизить нагрузку, но не заменяют профессиональную оценку. Индивидуальный режим лучше согласовать с врачом.",
            ),
        ):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["card"])
            card.append(Gtk.Label(label=title, xalign=0, css_classes=["section-title"]))
            card.append(Gtk.Label(label=text, xalign=0, wrap=True, css_classes=["body-copy"]))
            content.append(card)
        return scroller

    def refresh(self, rebuild_lists: bool = True) -> None:
        self._refresh_notification_center()
        set_status_banner_state(
            self.manual_pause_banner,
            bool(self.app.config.data["manual_pause"]),
        )
        activity = self.app.scheduler.read_activity()
        set_status_banner_state(
            self.screen_share_banner,
            bool(self.app.config.data.get("pause_on_screen_share", True)) and activity.screen_sharing,
        )
        set_status_banner_state(
            self.tracking_banner,
            self.app.scheduler.activity_source == "session",
        )
        self.wellness_card.set_visible(bool(self.app.config.data.get("wellness_checkin_enabled", True)))
        self.screen_value.set_text(format_duration(self.app.db.total_for_day(), self.language))
        done, _ = self.app.db.reminder_counts()
        self.breaks_value.set_text(str(done))
        enabled_due = [(kind, self.app.scheduler.next_due(kind)) for kind in REMINDER_META]
        enabled_due = [(kind, due) for kind, due in enabled_due if due is not None]
        quick_due = [(kind, due) for kind, due in enabled_due if kind in ("eyes", "general", "neck")]
        if quick_due:
            quick_kind, quick_seconds = min(quick_due, key=lambda item: float(item[1] or 0))
            self.quick_next_title.set_text(self.app.scheduler.next_title(quick_kind))
            self.quick_next_due.set_text(
                f"Automatic reminder in {format_duration(quick_seconds or 0, self.language)}"
                if self.language == "en"
                else f"Автоматическое напоминание через {format_duration(quick_seconds or 0, self.language)}"
            )
        else:
            self.quick_next_title.set_text(
                "No scheduled quick breaks" if self.language == "en" else "Нет запланированных быстрых пауз"
            )
            self.quick_next_due.set_text(
                "You can still start any option above"
                if self.language == "en"
                else "Любой вариант выше всё равно можно запустить"
            )
        visible_page = self.stack.get_visible_child_name()
        if hasattr(self, "breathing_today_value"):
            today_breathing = self.app.db.breathing_overview(1)
            week_breathing = self.app.db.breathing_overview(7)
            self.breathing_today_value.set_text(str(int(today_breathing["sessions"] or 0)))
            self.breathing_week_value.set_text(str(int(week_breathing["sessions"] or 0)))
            self.breathing_minutes_value.set_text(
                format_duration(float(week_breathing["seconds"] or 0), self.language)
            )
        if visible_page == "habits" and rebuild_lists:
            self._rebuild_habits()
        if visible_page == "training" and rebuild_lists:
            self._rebuild_training()
        if visible_page == "achievements" and rebuild_lists:
            self._rebuild_achievements()
        self.next_value.set_text(
            format_duration(min((due for _, due in enabled_due), default=0), self.language)
        )
        eye_due = self.app.scheduler.next_due("eyes")
        if self.app.config.data["manual_pause"]:
            self.hero_number.set_text("—")
            self.hero_unit.set_text("paused" if self.language == "en" else "пауза")
            self.hero_pause_button.set_icon_name("media-playback-start-symbolic")
            self.hero_pause_button.set_tooltip_text(
                "Resume timers" if self.language == "en" else "Продолжить таймеры"
            )
        elif eye_due is not None and eye_due < 60:
            self.hero_number.set_text(str(max(0, int(eye_due))))
            self.hero_unit.set_text("sec" if self.language == "en" else "сек")
            self.hero_pause_button.set_icon_name("media-playback-pause-symbolic")
            self.hero_pause_button.set_tooltip_text(
                "Pause timers" if self.language == "en" else "Приостановить таймеры"
            )
        else:
            self.hero_number.set_text(str(max(0, math.ceil((eye_due or 0) / 60))))
            self.hero_unit.set_text("min" if self.language == "en" else "мин")
            self.hero_pause_button.set_icon_name("media-playback-pause-symbolic")
            self.hero_pause_button.set_tooltip_text(
                "Pause timers" if self.language == "en" else "Приостановить таймеры"
            )

        if rebuild_lists and (visible_page == "today" or not self.reminder_due_labels):
            child = self.reminder_grid.get_first_child()
            while child:
                nxt = child.get_next_sibling()
                self.reminder_grid.remove(child)
                child = nxt
            self.reminder_due_labels.clear()
            self.reminder_title_labels.clear()
            for kind, due in enabled_due:
                box = Gtk.Box(
                    orientation=Gtk.Orientation.VERTICAL, spacing=6, css_classes=["card", "reminder-card"]
                )
                head = Gtk.Box(spacing=9)
                head.append(activity_icon(kind, 23, "reminder-icon-shell"))
                title = Gtk.Label(
                    label=self.app.scheduler.next_title(kind), xalign=0, css_classes=["card-title"]
                )
                due_prefix = "in" if self.language == "en" else "через"
                due_label = Gtk.Label(
                    label=f"{due_prefix} {format_duration(due or 0, self.language)}",
                    xalign=0,
                    css_classes=["accent-text"],
                )
                self.reminder_title_labels[kind] = title
                self.reminder_due_labels[kind] = due_label
                head.append(title)
                box.append(head)
                box.append(due_label)
                self.reminder_grid.append(box)
        else:
            due_map = dict(enabled_due)
            for kind, label in self.reminder_due_labels.items():
                if kind in due_map:
                    due_prefix = "in" if self.language == "en" else "через"
                    label.set_text(f"{due_prefix} {format_duration(due_map[kind] or 0, self.language)}")
                    self.reminder_title_labels[kind].set_text(self.app.scheduler.next_title(kind))

        if rebuild_lists and visible_page == "analytics":
            clear_box(self.apps_list)
            categories, apps = self._chart_categories()
            if not apps:
                row = Adw.ActionRow(
                    title="Статистика появится после нескольких минут работы",
                    subtitle="Сбор уже работает в фоне",
                )
                self.apps_list.append(row)
            else:
                total_apps = sum(float(row["seconds"]) for row in apps) or 1
                for category in categories:
                    app_id = category["app_id"]
                    share = float(category["seconds"]) / total_apps
                    share_text = "of screen time" if self.language == "en" else "экранного времени"
                    row = Adw.ActionRow(title=category["name"], subtitle=f"{share:.0%} {share_text}")
                    desktop = None
                    if app_id != "__other__":
                        try:
                            desktop = GioUnix.DesktopAppInfo.new(app_id)
                        except (TypeError, GLib.Error):
                            desktop = None
                    if desktop and desktop.get_icon():
                        app_icon = Gtk.Image.new_from_gicon(desktop.get_icon())
                    else:
                        app_icon = Gtk.Image.new_from_icon_name(
                            "view-app-grid-symbolic"
                            if app_id == "__other__"
                            else "application-x-executable-symbolic"
                        )
                    app_icon.set_pixel_size(28)
                    icon_shell = Gtk.CenterBox(
                        css_classes=["app-icon-shell"], halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER
                    )
                    icon_shell.set_center_widget(app_icon)
                    row.add_prefix(icon_shell)
                    row.add_prefix(ColorSwatch(category["color"]))
                    row.add_suffix(
                        Gtk.Label(
                            label=format_duration(float(category["seconds"]), self.language),
                            width_chars=9,
                            xalign=1,
                        )
                    )
                    visible = app_id not in self.analytics_hidden_apps
                    toggle = Gtk.ToggleButton(
                        active=visible,
                        icon_name="view-reveal-symbolic" if visible else "view-conceal-symbolic",
                        tooltip_text="Show on chart" if self.language == "en" else "Показывать на графике",
                        css_classes=["chart-toggle"],
                        valign=Gtk.Align.CENTER,
                    )
                    toggle.connect("toggled", self._analytics_visibility_changed, app_id)
                    row.add_suffix(toggle)
                    row.set_activatable_widget(toggle)
                    row.set_opacity(1.0 if visible else 0.55)
                    self.apps_list.append(row)
            self.chart.set_categories(categories, self.analytics_hidden_apps)
            self.day_chart.set_categories(categories, self.analytics_hidden_apps)

            overview = self.app.db.exercise_overview(7)
            done_total = int(overview["done"] or 0)
            snoozed_total = int(overview["snoozed"] or 0)
            self.exercise_time_value.set_text(format_duration(float(overview["seconds"] or 0), self.language))
            self.exercise_done_value.set_text(str(done_total))
            self.exercise_snoozed_value.set_text(str(snoozed_total))
            attempts = done_total + snoozed_total
            self.exercise_rate_value.set_text(f"{round(done_total * 100 / attempts)}%" if attempts else "—")
            clear_box(self.exercise_list)
            activities = self.app.db.exercise_by_kind(7)
            if not activities:
                empty = Gtk.Box(
                    orientation=Gtk.Orientation.VERTICAL, spacing=3, css_classes=["exercise-result-card"]
                )
                empty.append(
                    Gtk.Label(
                        label=self._t("Здесь появятся выполненные упражнения"),
                        xalign=0,
                        css_classes=["exercise-row-title"],
                    )
                )
                empty.append(
                    Gtk.Label(
                        label=self._t("Время начнёт считаться после кнопки «Начать упражнение»"),
                        xalign=0,
                        wrap=True,
                        css_classes=["muted", "caption"],
                    )
                )
                self.exercise_list.append(empty)
            else:
                for item in activities:
                    kind = str(item["kind"])
                    if kind not in REMINDER_META:
                        continue
                    done_count = int(item["done"] or 0)
                    snoozed_count = int(item["snoozed"] or 0)
                    seconds = float(item["seconds"] or 0)
                    self.exercise_list.append(
                        self._exercise_result_row(kind, done_count, snoozed_count, seconds)
                    )

            range_start = self.wellness_range_start.isoformat()
            range_end = self.wellness_range_end.isoformat()
            calendar_days = (self.wellness_range_end - self.wellness_range_start).days + 1
            summary = self.app.db.wellness_summary_between(range_start, range_end)
            recorded_days = int(summary["recorded_days"] or 0)
            self.wellness_stamp.set_text(
                f"Average from {recorded_days} recorded day{'s' if recorded_days != 1 else ''} across the selected {calendar_days}-day range · lower is better"
                if self.language == "en"
                else f"Среднее по {recorded_days} дн. с оценками за выбранный период в {calendar_days} дн. · меньше — лучше"
            )
            for key, bar in self.wellness_bars.items():
                value = float(summary[key] or 0)
                bar.set_value(value)
                self.wellness_score_labels[key].set_text(f"{value:.1f} / 10" if recorded_days else "—")
            self.wellness_screen_value.set_text(
                format_duration(self.app.db.total_between(range_start, range_end), self.language)
            )
            range_exercise = self.app.db.exercise_overview_between(range_start, range_end)
            self.wellness_breaks_value.set_text(str(int(range_exercise["done"] or 0)))
            self.wellness_exercise_value.set_text(
                format_duration(float(range_exercise["seconds"] or 0), self.language)
            )
            current, previous = self.app.db.wellness_range_comparison(
                self.wellness_range_start, self.wellness_range_end
            )
            if not current:
                self.wellness_insight.set_text(
                    "There are no wellbeing check-ins in the selected range. Choose another range or add a check-in from the Today page."
                    if self.language == "en"
                    else "В выбранном периоде нет оценок самочувствия. Выберите другой период или добавьте отметку на главном экране."
                )
            elif not previous:
                self.wellness_insight.set_text(
                    "A trend needs check-ins in the preceding period of the same length. The app compares periods without claiming what caused the change."
                    if self.language == "en"
                    else "Для динамики нужны оценки в предыдущем периоде такой же длины. Приложение сравнивает периоды, не приписывая изменению конкретную причину."
                )
            else:
                keys = ("headache", "eyes", "neck", "back")
                current_average = sum(float(current[key]) for key in keys) / len(keys)
                previous_average = sum(float(previous[key]) for key in keys) / len(keys)
                delta = current_average - previous_average
                if abs(delta) < 0.25:
                    message = (
                        "The average score is nearly unchanged from the preceding period."
                        if self.language == "en"
                        else "Средняя оценка почти не изменилась относительно предыдущего периода."
                    )
                elif delta < 0:
                    message = (
                        f"The average score is {abs(delta):.1f} lower than in the preceding period."
                        if self.language == "en"
                        else f"Средняя оценка на {abs(delta):.1f} ниже, чем в предыдущем периоде."
                    )
                else:
                    message = (
                        f"The average score is {delta:.1f} higher than in the preceding period."
                        if self.language == "en"
                        else f"Средняя оценка на {delta:.1f} выше, чем в предыдущем периоде."
                    )
                self.wellness_insight.set_text(message)
            self._update_wellness_header()

        self._translate_tree(self)

    def _page_changed(self, _stack: Gtk.Stack, _pspec: Any) -> None:
        if self.stack.get_visible_child_name() == "training":
            self.training_view = "active" if self.app.db.active_training() is not None else "setup"
            if self.training_view == "setup":
                self.training_setup_step = 0
            self._rebuild_training()
        self.refresh(rebuild_lists=True)

    def _toggle_manual_pause(self, _button: Gtk.Button) -> None:
        self.app.config.data["manual_pause"] = not bool(self.app.config.data["manual_pause"])
        self.app.config.save()
        self.refresh()

    def apply_theme_state(self, dark: bool) -> None:
        mode = str(self.app.config.data.get("theme_mode", "light"))
        self._syncing_theme_control = True
        self.theme_switch.set_active(dark)
        self.theme_switch.set_sensitive(mode != "auto")
        if hasattr(self, "theme_mode_picker"):
            self.theme_mode_picker.set_selected(("light", "dark", "auto").index(mode))
            self.theme_schedule.set_sensitive(mode == "auto")
        self._syncing_theme_control = False
        if mode == "auto":
            label = "Automatic theme" if self.language == "en" else "Автотема"
        else:
            label = "Dark theme" if self.language == "en" else "Тёмная тема"
        self.theme_label.set_text(label)
        self.theme_icon.set_from_icon_name(
            "weather-clear-night-symbolic" if dark else "weather-clear-symbolic"
        )
        if dark:
            self.add_css_class("dark-mode")
        else:
            self.remove_css_class("dark-mode")
        self.backdrop.set_dark(dark)
        self.apply_palette_state()

    def apply_palette_state(self) -> None:
        palette = normalize_color_theme(self.app.config.data.get("color_theme"))
        self.backdrop.set_color_theme(palette)
        if hasattr(self, "breathing_orb"):
            self.breathing_orb.set_color_theme(palette)

    def _theme_changed(self, switch: Gtk.Switch, _pspec: Any) -> None:
        if self._syncing_theme_control:
            return
        dark = switch.get_active()
        self.app.config.data["dark_mode"] = dark
        self.app.config.data["theme_mode"] = "dark" if dark else "light"
        self.app.config.save()
        self.app.apply_color_scheme()
        self.refresh()

    def _enabled_changed(self, switch: Gtk.Switch, _pspec: Any, kind: str) -> None:
        self.app.config.reminder(kind)["enabled"] = switch.get_active()
        self.app.config.save()
        self.refresh()

    def _interval_changed(self, spin: Gtk.SpinButton, kind: str) -> None:
        key = "times_per_day" if kind == "drops" else "interval_minutes"
        self.app.config.reminder(kind)[key] = int(spin.get_value())
        self.app.config.save()
        self.refresh()

    def _fullscreen_changed(self, row: Adw.SwitchRow, _pspec: Any) -> None:
        self.app.config.data["pause_on_fullscreen"] = row.get_active()
        self.app.config.save()

    def _idle_changed(self, spin: Gtk.SpinButton) -> None:
        self.app.config.data["idle_threshold_seconds"] = int(spin.get_value())
        self.app.config.save()

    def _on_close(self, _window: Gtk.Window) -> bool:
        self.set_visible(False)
        return True


class TrainingSessionOverlay(Gtk.ApplicationWindow):
    """Fullscreen course runner with automatic timed stages and explicit rep confirmation."""

    def __init__(
        self,
        app: ZdorovoApplication,
        plan: dict[str, Any],
        course: dict[str, Any],
        on_complete: Callable[[float], None],
    ) -> None:
        super().__init__(application=app, decorated=False, title=str(plan["title"]))
        self.plan = plan
        self.course = course
        self.on_complete = on_complete
        self.language = str(app.config.data.get("language", "en"))
        self.dark = bool(app.config.data.get("dark_mode", False))
        self.stages = training_stages(plan)
        self.stage_index = -1
        self.stage_remaining: float | None = 5.0
        self.stage_duration = 5.0
        self.session_elapsed = 0.0
        self.last_tick = time.monotonic()
        self.running = True
        self.completed = False
        self.timer_source: int | None = None
        # A workout is user-initiated and may intentionally run alongside
        # music, a video or spoken guidance from another application.
        self.paused_players: list[str] = []
        self.add_css_class("break-window")
        self.add_css_class("training-runner-window")
        if self.dark:
            self.add_css_class("break-dark")
            self.add_css_class("dark-mode")
        parent = app.window
        if isinstance(parent, Gtk.Window):
            self.set_transient_for(parent)
            parent_width = parent.get_width() or 1060
            parent_height = parent.get_height() or 720
            self.set_default_size(max(560, parent_width), max(520, parent_height))
        else:
            self.set_default_size(1060, 720)
        self.set_resizable(True)
        self.set_size_request(720, 520)
        self.set_modal(True)

        stage = Gtk.Overlay()
        stage.set_child(BlurredWallpaper(self.dark))
        frame = Gtk.CenterBox(orientation=Gtk.Orientation.VERTICAL, css_classes=["training-runner-bg"])
        frame.set_hexpand(True)
        frame.set_vexpand(True)
        clamp = Adw.Clamp(maximum_size=1180, tightening_threshold=920)
        clamp.set_vexpand(True)
        card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            css_classes=["training-runner-card"],
        )
        card.set_vexpand(True)
        card.set_margin_top(12)
        card.set_margin_bottom(12)
        card.set_margin_start(12)
        card.set_margin_end(12)

        head = Gtk.Box(spacing=12, css_classes=["training-runner-head"])
        heading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
        heading.append(
            Gtk.Label(
                label=training_copy(course, "title", self.language),
                xalign=0,
                css_classes=["training-runner-course"],
            )
        )
        heading.append(
            Gtk.Label(
                label=(
                    f"Day {int(plan['course_day'])} of {int(plan['total_days'])} · {plan['fitness_title']}"
                    if self.language == "en"
                    else f"День {int(plan['course_day'])} из {int(plan['total_days'])} · {plan['fitness_title']}"
                ),
                xalign=0,
                css_classes=["muted", "caption"],
            )
        )
        head.append(heading)
        self.session_clock = Gtk.Label(label="00:00", css_classes=["training-runner-session-clock"])
        head.append(self.session_clock)
        close = Gtk.Button(
            icon_name="window-close-symbolic",
            tooltip_text="End workout" if self.language == "en" else "Завершить тренировку",
            css_classes=["training-runner-close"],
        )
        close.set_focusable(False)
        close.connect("clicked", self._request_close)
        head.append(close)
        card.append(head)
        self.overall_progress = Gtk.ProgressBar(css_classes=["training-runner-overall-progress"])
        card.append(self.overall_progress)

        content = Gtk.Box(spacing=24, css_classes=["training-runner-content"])
        content.set_vexpand(True)
        self.picture = Gtk.Picture(css_classes=["training-runner-picture"])
        self.picture.set_content_fit(Gtk.ContentFit.COVER)
        self.picture.set_can_shrink(True)
        self.picture.set_size_request(360, 270)
        content.append(self.picture)

        copy = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
            hexpand=True,
            valign=Gtk.Align.CENTER,
            css_classes=["training-runner-copy"],
        )
        self.stage_caption = Gtk.Label(xalign=0, css_classes=["training-runner-kicker"])
        copy.append(self.stage_caption)
        self.stage_title = Gtk.Label(
            xalign=0,
            wrap=True,
            css_classes=["training-runner-title"],
        )
        copy.append(self.stage_title)
        self.stage_value = Gtk.Label(xalign=0, css_classes=["training-runner-value"])
        copy.append(self.stage_value)
        self.stage_progress = Gtk.ProgressBar(css_classes=["training-runner-stage-progress"])
        copy.append(self.stage_progress)
        self.stage_instruction = Gtk.Label(
            xalign=0,
            wrap=True,
            css_classes=["training-runner-instruction"],
        )
        copy.append(self.stage_instruction)
        self.stage_cue = Gtk.Label(
            xalign=0,
            wrap=True,
            css_classes=["training-runner-cue"],
        )
        copy.append(self.stage_cue)
        self.next_stage = Gtk.Label(
            xalign=0,
            wrap=True,
            css_classes=["training-runner-next"],
        )
        copy.append(self.next_stage)
        content.append(copy)
        content_scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            css_classes=["training-runner-scroll"],
        )
        content_scroll.set_overlay_scrolling(True)
        content_scroll.set_hexpand(True)
        content_scroll.set_vexpand(True)
        content_scroll.set_child(content)
        card.append(content_scroll)

        actions = Gtk.Box(spacing=10, halign=Gtk.Align.END, css_classes=["training-runner-actions"])
        actions.set_hexpand(True)
        actions.set_valign(Gtk.Align.END)
        self.pause_button = Gtk.Button(css_classes=["break-button", "break-secondary"])
        self.pause_button.set_size_request(170, 46)
        self._set_button(
            self.pause_button,
            "media-playback-pause-symbolic",
            "Pause" if self.language == "en" else "Пауза",
        )
        self.pause_button.set_focusable(False)
        self.pause_button.connect("clicked", self._toggle_pause)
        actions.append(self.pause_button)
        self.primary_button = Gtk.Button(css_classes=["break-button", "break-primary"])
        self.primary_button.set_size_request(220, 46)
        self.primary_button.set_focusable(False)
        self.primary_button.connect("clicked", self._primary_clicked)
        actions.append(self.primary_button)
        card.append(actions)
        card.append(cyberjabka_footer("overlay-footer"))
        clamp.set_child(card)
        frame.set_center_widget(clamp)
        stage.add_overlay(frame)
        self.set_child(stage)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._block_action_keys)
        self.add_controller(keys)
        self.connect("close-request", self._on_close_request)
        self.connect("destroy", self._cleanup)
        self._render_stage()
        play_guidance_sound(app.config.data, "start")
        self.timer_source = GLib.timeout_add(100, self._tick)

    @staticmethod
    def _set_button(button: Gtk.Button, icon_name: str, text: str) -> None:
        content = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        content.append(Gtk.Image.new_from_icon_name(icon_name))
        content.append(Gtk.Label(label=text))
        button.set_child(content)

    @staticmethod
    def _clock(value: float) -> str:
        seconds = max(0, int(math.ceil(value)))
        minutes, remainder = divmod(seconds, 60)
        return f"{minutes:02d}:{remainder:02d}"

    def _current(self) -> dict[str, Any] | None:
        if 0 <= self.stage_index < len(self.stages):
            return self.stages[self.stage_index]
        return None

    def _exercise_position(self) -> tuple[int, int]:
        total = sum(1 for item in self.stages if item["type"] == "exercise")
        completed = sum(
            1
            for index, item in enumerate(self.stages)
            if item["type"] == "exercise" and index < self.stage_index
        )
        current = self._current()
        if current and current["type"] == "exercise":
            completed += 1
        return completed, max(1, total)

    def _next_exercise(self) -> dict[str, Any] | None:
        for item in self.stages[self.stage_index + 1 :]:
            if item["type"] == "exercise":
                return item
        return None

    def _set_picture(self, image_name: str | None) -> None:
        path = ASSET_ROOT / image_name if image_name else None
        if path and path.exists():
            self.picture.set_filename(str(path))
            self.picture.set_visible(True)
        else:
            self.picture.set_visible(False)

    def _render_stage(self) -> None:
        current = self._current()
        completed, total = self._exercise_position()
        self.overall_progress.set_fraction(min(1.0, completed / total))
        if self.stage_index < 0:
            self.stage_caption.set_text("PREPARATION" if self.language == "en" else "ПОДГОТОВКА")
            self.stage_title.set_text("Get into position" if self.language == "en" else "Приготовьтесь")
            self.stage_value.set_text(self._clock(self.stage_remaining or 0))
            self.stage_instruction.set_text(
                "Clear a safe space. The first exercise will begin automatically."
                if self.language == "en"
                else "Освободите безопасное место. Первое упражнение начнётся автоматически."
            )
            self.stage_cue.set_text(
                "Stop the session if pain, numbness, weakness, dizziness or loss of coordination appears."
                if self.language == "en"
                else "Остановите тренировку при боли, онемении, слабости, головокружении или нарушении координации."
            )
            self._set_picture(str(self.course.get("image", "")))
            self.primary_button.set_visible(True)
            self._set_button(
                self.primary_button,
                "media-playback-start-symbolic",
                "Start now" if self.language == "en" else "Начать сейчас",
            )
            self.next_stage.set_text("")
        elif current is None:
            return
        elif current["type"] == "exercise":
            round_copy = (
                f" · round {current['round']} of {current['rounds']}"
                if int(current["rounds"]) > 1 and self.language == "en"
                else f" · круг {current['round']} из {current['rounds']}"
                if int(current["rounds"]) > 1
                else ""
            )
            self.stage_caption.set_text(
                (f"EXERCISE {completed} OF {total}{round_copy}").upper()
                if self.language == "en"
                else (f"УПРАЖНЕНИЕ {completed} ИЗ {total}{round_copy}").upper()
            )
            self.stage_title.set_text(str(current["title"]))
            self.stage_value.set_text(
                self._clock(self.stage_remaining or 0) if current["timed"] else str(current["target"])
            )
            self.stage_instruction.set_text(str(current["instruction"]))
            self.stage_cue.set_text(str(current["cue"]))
            self._set_picture(str(current.get("image", "")))
            self.primary_button.set_visible(True)
            if current["timed"]:
                self._set_button(
                    self.primary_button,
                    "object-select-symbolic",
                    "Done" if self.language == "en" else "Выполнено",
                )
            else:
                self._set_button(
                    self.primary_button,
                    "object-select-symbolic",
                    (
                        f"Completed · {current['target']}"
                        if self.language == "en"
                        else f"Выполнено · {current['target']}"
                    ),
                )
            following = self._next_exercise()
            self.next_stage.set_text(
                f"Next after recovery: {following['title']}"
                if following and self.language == "en"
                else f"После отдыха: {following['title']}"
                if following
                else "Final recovery follows"
                if self.language == "en"
                else "Далее — финальное восстановление"
            )
        elif current["type"] == "rest":
            self.stage_caption.set_text("RECOVERY" if self.language == "en" else "ОТДЫХ")
            self.stage_title.set_text(
                "Recover before the next exercise"
                if self.language == "en"
                else "Восстановитесь перед следующим упражнением"
            )
            self.stage_value.set_text(self._clock(self.stage_remaining or 0))
            self.stage_instruction.set_text(
                "Breathe normally, relax the working muscles and change position calmly."
                if self.language == "en"
                else "Дышите свободно, расслабьте работавшие мышцы и спокойно смените положение."
            )
            self.stage_cue.set_text(
                f"Next: {current['next_title']} · {current['next_target']}"
                if self.language == "en"
                else f"Далее: {current['next_title']} · {current['next_target']}"
            )
            self.next_stage.set_text(
                "The next exercise starts automatically."
                if self.language == "en"
                else "Следующее упражнение начнётся автоматически."
            )
            self._set_picture(str(current.get("next_image", "")))
            self._set_button(
                self.primary_button,
                "go-next-symbolic",
                "Continue" if self.language == "en" else "Продолжить",
            )
            self.primary_button.set_visible(True)
        else:
            self.stage_caption.set_text("FINAL RECOVERY" if self.language == "en" else "ЗАВЕРШЕНИЕ")
            self.stage_title.set_text(
                "Let your breathing settle" if self.language == "en" else "Восстановите дыхание"
            )
            self.stage_value.set_text(self._clock(self.stage_remaining or 0))
            self.stage_instruction.set_text(
                "Stand comfortably and make gentle ankle or shoulder movements. The training day will be saved when this timer ends."
                if self.language == "en"
                else "Спокойно постойте и мягко подвигайте стопами или плечами. День сохранится после окончания таймера."
            )
            self.stage_cue.set_text(
                "No stretching through pain and no forced breathing."
                if self.language == "en"
                else "Не растягивайтесь через боль и не форсируйте дыхание."
            )
            self.next_stage.set_text("")
            self._set_picture(str(self.course.get("image", "")))
            self._set_button(
                self.primary_button,
                "object-select-symbolic",
                "Finish workout" if self.language == "en" else "Завершить тренировку",
            )
            self.primary_button.set_visible(True)
        self._update_progress()

    def _update_progress(self) -> None:
        if self.stage_remaining is None or self.stage_duration <= 0:
            self.stage_progress.set_fraction(0.0)
        else:
            self.stage_progress.set_fraction(
                max(0.0, min(1.0, 1.0 - self.stage_remaining / self.stage_duration))
            )
            self.stage_value.set_text(self._clock(self.stage_remaining))
        self.session_clock.set_text(self._clock(self.session_elapsed))
        self.primary_button.set_sensitive(self.running)

    def _advance(self) -> None:
        self.stage_index += 1
        if self.stage_index >= len(self.stages):
            self._complete()
            return
        current = self.stages[self.stage_index]
        duration = current.get("duration_seconds")
        self.stage_remaining = float(duration) if duration is not None else None
        self.stage_duration = float(duration or 0)
        play_guidance_sound(self.get_application().config.data, "step")
        self._render_stage()

    def _tick(self) -> bool:
        if self.completed:
            self.timer_source = None
            return GLib.SOURCE_REMOVE
        now = time.monotonic()
        delta = min(1.0, max(0.0, now - self.last_tick))
        self.last_tick = now
        if not self.running:
            return GLib.SOURCE_CONTINUE
        self.session_elapsed += delta
        if self.stage_remaining is not None:
            self.stage_remaining = max(0.0, self.stage_remaining - delta)
            if self.stage_remaining <= 0:
                self._advance()
                return GLib.SOURCE_CONTINUE if not self.completed else GLib.SOURCE_REMOVE
        self._update_progress()
        return GLib.SOURCE_CONTINUE

    def _primary_clicked(self, _button: Gtk.Button) -> None:
        if self.completed:
            self.destroy()
            return
        if not self.running:
            return
        if self.stage_index < 0:
            self._advance()
            return
        current = self._current()
        if current is None:
            return
        self._advance()

    def _toggle_pause(self, _button: Gtk.Button) -> None:
        if self.completed:
            return
        self.running = not self.running
        self.last_tick = time.monotonic()
        self._set_button(
            self.pause_button,
            "media-playback-pause-symbolic" if self.running else "media-playback-start-symbolic",
            ("Pause" if self.language == "en" else "Пауза")
            if self.running
            else ("Continue" if self.language == "en" else "Продолжить"),
        )
        self._update_progress()

    def _complete(self) -> None:
        if self.completed:
            return
        self.completed = True
        self.running = False
        if self.timer_source is not None:
            GLib.source_remove(self.timer_source)
            self.timer_source = None
        self.on_complete(max(1.0, self.session_elapsed))
        self._resume_media()
        self.overall_progress.set_fraction(1.0)
        self.stage_progress.set_fraction(1.0)
        self.stage_caption.set_text("WORKOUT COMPLETE" if self.language == "en" else "ТРЕНИРОВКА ЗАВЕРШЕНА")
        self.stage_title.set_text("Course day saved" if self.language == "en" else "День курса сохранён")
        self.stage_value.set_text(self._clock(self.session_elapsed))
        self.stage_instruction.set_text(
            "The next course day will open tomorrow. Today’s result is already in the calendar."
            if self.language == "en"
            else "Следующий день курса откроется завтра. Сегодняшний результат уже отмечен в календаре."
        )
        self.stage_cue.set_text(
            "Keep only exercise that continues to feel comfortable."
            if self.language == "en"
            else "Оставляйте только ту нагрузку, которая остаётся комфортной."
        )
        self.next_stage.set_text("")
        self.pause_button.set_visible(False)
        self.primary_button.set_visible(True)
        self.primary_button.set_sensitive(True)
        self._set_button(
            self.primary_button,
            "window-close-symbolic",
            "Close" if self.language == "en" else "Закрыть",
        )

    def _request_close(self, _button: Gtk.Button | None = None) -> None:
        if self.completed:
            self.destroy()
            return
        dialog = Adw.MessageDialog.new(
            self,
            "End this workout?" if self.language == "en" else "Завершить тренировку?",
            (
                "This unfinished session will not advance the course or appear as completed in the calendar."
                if self.language == "en"
                else "Незавершённая тренировка не продвинет курс и не появится в календаре как выполненная."
            ),
        )
        dialog.add_response("continue", "Continue workout" if self.language == "en" else "Продолжить")
        dialog.add_response("end", "End without saving" if self.language == "en" else "Выйти без сохранения")
        dialog.set_response_appearance("end", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("continue")
        dialog.set_close_response("continue")
        dialog.connect(
            "response",
            lambda _dialog, response: self.destroy() if response == "end" else None,
        )
        dialog.present()

    def _on_close_request(self, _window: Gtk.Window) -> bool:
        self._request_close()
        return True

    def _resume_media(self) -> None:
        if self.paused_players:
            players = self.paused_players
            self.paused_players = []
            resume_media_players(players)

    def _cleanup(self, _window: Gtk.Window) -> None:
        if self.timer_source is not None:
            GLib.source_remove(self.timer_source)
            self.timer_source = None
        self._resume_media()

    @staticmethod
    def _block_action_keys(
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        return keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space)


class FallbackOverlay(Gtk.ApplicationWindow):
    def __init__(self, app: ZdorovoApplication, payload: dict[str, Any]) -> None:
        super().__init__(application=app, decorated=False, title=payload["title"])
        self.payload = payload
        self.language = str(app.config.data.get("language", "en"))
        self.dark = bool(app.config.data.get("dark_mode", False))
        self.add_css_class("break-window")
        if self.dark:
            self.add_css_class("break-dark")
        self.duration_seconds = max(1, int(payload.get("duration_seconds", 20)))
        self.step_seconds = guided_step_seconds(
            self.duration_seconds, len(payload["steps"]), payload.get("step_seconds")
        )
        self.elapsed = 0.0
        self.run_started = 0.0
        self.started = False
        self.running = False
        self.finished = False
        self.current_step = -1
        self.timer_source: int | None = None
        self.fullscreen()
        self.set_modal(True)
        stage = Gtk.Overlay()
        stage.set_child(BlurredWallpaper(self.dark))
        frame = Gtk.CenterBox(orientation=Gtk.Orientation.VERTICAL, css_classes=["overlay-bg"])
        frame.set_hexpand(True)
        frame.set_vexpand(True)
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, css_classes=["break-card"])
        card.set_size_request(980, -1)
        card.set_halign(Gtk.Align.CENTER)
        card.set_valign(Gtk.Align.CENTER)
        card.append(Gtk.Label(label=payload["eyebrow"].upper(), xalign=0, css_classes=["overlay-kicker"]))
        card.append(Gtk.Label(label=payload["title"], xalign=0, wrap=True, css_classes=["overlay-title"]))

        timer_panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7, css_classes=["guided-timer"])
        timer_head = Gtk.Box(spacing=12)
        self.timer_caption = Gtk.Label(
            label=self._t("Нажмите «Начать упражнение» — этапы и время приложение отсчитает само."),
            xalign=0,
            hexpand=True,
            wrap=True,
            css_classes=["guided-caption"],
        )
        self.timer_value = Gtk.Label(label=self._clock(self.duration_seconds), css_classes=["guided-time"])
        timer_head.append(self.timer_caption)
        timer_head.append(self.timer_value)
        timer_panel.append(timer_head)
        self.timer_progress = Gtk.ProgressBar(fraction=0.0, css_classes=["guided-progress"])
        timer_panel.append(self.timer_progress)
        card.append(timer_panel)

        body = Gtk.Box(spacing=24)
        image_name = payload.get("image")
        image_path = ASSET_ROOT / image_name if image_name else None
        if image_path and image_path.exists():
            picture = Gtk.Picture.new_for_filename(str(image_path))
            picture.set_content_fit(Gtk.ContentFit.COVER)
            picture.set_size_request(300, 300)
            picture.add_css_class("guide-picture")
            body.append(picture)
        steps = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=9, hexpand=True, valign=Gtk.Align.CENTER
        )
        self.step_labels: list[Gtk.Label] = []
        for index, step in enumerate(payload["steps"], 1):
            label = Gtk.Label(label=f"{index}.  {step}", xalign=0, wrap=True, css_classes=["overlay-step"])
            self.step_labels.append(label)
            steps.append(label)
        body.append(steps)
        card.append(body)
        card.append(Gtk.Label(label=payload["note"], xalign=0, wrap=True, css_classes=["overlay-note"]))
        actions = Gtk.Box(spacing=12, halign=Gtk.Align.END)
        actions.add_css_class("break-actions")
        self.snooze_button = Gtk.Button(css_classes=["break-button", "break-secondary"])
        snooze_minutes = int(app.config.data.get("snooze_minutes", 5))
        self._set_button(
            self.snooze_button, "alarm-symbolic", snooze_button_text(snooze_minutes, self.language)
        )
        self.pause_button = Gtk.Button(css_classes=["break-button", "break-secondary"], visible=False)
        self._set_button(self.pause_button, "media-playback-pause-symbolic", self._t("Пауза"))
        self.primary_button = Gtk.Button(css_classes=["break-button", "break-primary"])
        self._set_button(self.primary_button, "media-playback-start-symbolic", self._t("Начать упражнение"))
        self.snooze_button.set_size_request(230, 46)
        self.pause_button.set_size_request(130, 46)
        self.primary_button.set_size_request(190, 46)
        for button in (self.snooze_button, self.pause_button, self.primary_button):
            button.set_focusable(False)
            button.set_receives_default(False)
        self.snooze_button.connect("clicked", lambda _b: self.respond("snooze"))
        self.pause_button.connect("clicked", self._toggle_timer)
        self.primary_button.connect("clicked", self._primary_clicked)
        actions.append(self.snooze_button)
        actions.append(self.pause_button)
        actions.append(self.primary_button)
        card.append(actions)
        card.append(cyberjabka_footer("overlay-footer"))
        frame.set_center_widget(card)
        stage.add_overlay(frame)
        self.set_child(stage)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._block_action_keys)
        self.add_controller(keys)
        self.connect("destroy", self._cleanup_timer)

    @staticmethod
    def _clock(seconds: float) -> str:
        value = max(0, int(math.ceil(seconds)))
        minutes, rest = divmod(value, 60)
        return f"{minutes:02d}:{rest:02d}"

    def _t(self, russian: str) -> str:
        return localized_text(self.language, russian)

    @staticmethod
    def _set_button(button: Gtk.Button, icon_name: str, text: str) -> None:
        content = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        content.append(Gtk.Image.new_from_icon_name(icon_name))
        content.append(Gtk.Label(label=text))
        button.set_child(content)

    def _elapsed_now(self) -> float:
        return self.elapsed + (time.monotonic() - self.run_started if self.running else 0.0)

    def _primary_clicked(self, _button: Gtk.Button) -> None:
        if not self.started:
            self.started = True
            self.running = True
            self.run_started = time.monotonic()
            self.snooze_button.set_visible(False)
            self.pause_button.set_visible(True)
            self._set_button(self.primary_button, "object-select-symbolic", self._t("Завершить"))
            play_guidance_sound(self.get_application().config.data, "start")
            self.timer_source = GLib.timeout_add(200, self._timer_tick)
            self._timer_tick()
            return
        self.respond("done")

    def _toggle_timer(self, _button: Gtk.Button) -> None:
        if self.finished:
            return
        if self.running:
            self.elapsed = self._elapsed_now()
            self.running = False
            self._set_button(self.pause_button, "media-playback-start-symbolic", self._t("Продолжить"))
            self.timer_caption.set_text(self._t("Таймер приостановлен"))
        else:
            self.running = True
            self.run_started = time.monotonic()
            self._set_button(self.pause_button, "media-playback-pause-symbolic", self._t("Пауза"))
            self._timer_tick()

    def _timer_tick(self) -> bool:
        elapsed = min(self._elapsed_now(), float(self.duration_seconds))
        remaining = self.duration_seconds - elapsed
        self.timer_value.set_text(self._clock(remaining))
        self.timer_progress.set_fraction(min(1.0, elapsed / self.duration_seconds))

        cumulative = 0
        step_index = max(0, len(self.step_labels) - 1)
        for index, seconds in enumerate(self.step_seconds):
            cumulative += seconds
            if elapsed < cumulative:
                step_index = index
                break
        if step_index != self.current_step and self.step_labels:
            previous = self.current_step
            self.current_step = step_index
            for index, label in enumerate(self.step_labels):
                label.remove_css_class("overlay-step-current")
                label.remove_css_class("overlay-step-done")
                if index < step_index:
                    label.add_css_class("overlay-step-done")
                elif index == step_index:
                    label.add_css_class("overlay-step-current")
            if previous >= 0:
                play_guidance_sound(self.get_application().config.data, "step")
        if self.running:
            if self.language == "en":
                self.timer_caption.set_text(f"Current: step {step_index + 1} of {len(self.step_labels)}")
            else:
                self.timer_caption.set_text(f"Сейчас: шаг {step_index + 1} из {len(self.step_labels)}")

        if remaining <= 0:
            self.elapsed = float(self.duration_seconds)
            self.running = False
            self.finished = True
            self.timer_value.set_text("00:00")
            self.timer_caption.set_text(self._t("Упражнение завершено"))
            self.pause_button.set_visible(False)
            self._set_button(self.primary_button, "object-select-symbolic", self._t("Готово"))
            for label in self.step_labels:
                label.remove_css_class("overlay-step-current")
                label.add_css_class("overlay-step-done")
            play_guidance_sound(self.get_application().config.data, "done")
            self.timer_source = None
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _cleanup_timer(self, _window: Gtk.Window) -> None:
        if self.timer_source is not None:
            GLib.source_remove(self.timer_source)
            self.timer_source = None

    def _block_action_keys(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        return keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space)

    def respond(self, action: str) -> None:
        guided_seconds = self._elapsed_now() if action == "done" and self.started else 0.0
        if action in ("done", "snooze"):
            self.get_application().scheduler.resume_paused_media()
        atomic_json(
            RESPONSE_FILE,
            {
                "id": self.payload["id"],
                "action": action,
                "duration_seconds": min(float(self.duration_seconds), guided_seconds),
                "timestamp": time.time(),
            },
        )
        self.destroy()


class ZdorovoApplication(Adw.Application):
    def __init__(self, background: bool = False, trigger: str | None = None) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.background = background
        self.trigger_kind = trigger
        self.config = Config()
        set_active_color_theme(str(self.config.data.get("color_theme", "teal")))
        self.db = UsageDatabase()
        self.window: MainWindow | None = None
        self.overlay: FallbackOverlay | None = None
        self._css_provider: Gtk.CssProvider | None = None
        self._restore_window_after_overlay = False
        self.scheduler = Scheduler(
            self.config,
            self.db,
            self._show_reminder,
            self._scheduler_changed,
            background_tracking=True,
            prompt_wellness=self._prompt_wellness,
            prompt_habit=self._prompt_habit,
            prompt_training=self._prompt_training,
        )
        self._last_ui_refresh = 0.0
        self._last_achievement_check = 0.0

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        set_active_color_theme(str(self.config.data.get("color_theme", "teal")))
        Gtk.Window.set_default_icon_name(APP_ICON_NAME)
        self.apply_color_scheme()
        self.hold()
        self._load_css()
        ensure_expanded_system_notifications()
        if not bool(self.config.data.get("notification_center_initialized", False)):
            language = str(self.config.data.get("language", "en"))
            self.db.add_notification(
                "info",
                "Notification centre is ready" if language == "en" else "Центр уведомлений готов",
                (
                    "Habit reminders, wellbeing check-ins and completed breathing sessions will appear here."
                    if language == "en"
                    else "Здесь будут появляться напоминания о привычках, самочувствии и завершённых дыхательных сессиях."
                ),
                "habits",
                notification_id="notification-centre-welcome",
            )
            self.config.data["notification_center_initialized"] = True
            self.config.save()
        trigger_action = Gio.SimpleAction.new("trigger", GLib.VariantType.new("s"))
        trigger_action.connect("activate", self._trigger_action)
        self.add_action(trigger_action)
        respond_action = Gio.SimpleAction.new("respond", GLib.VariantType.new("s"))
        respond_action.connect("activate", self._respond_action)
        self.add_action(respond_action)
        theme_action = Gio.SimpleAction.new("set-dark-mode", GLib.VariantType.new("b"))
        theme_action.connect("activate", self._theme_action)
        self.add_action(theme_action)
        pause_action = Gio.SimpleAction.new("set-manual-pause", GLib.VariantType.new("b"))
        pause_action.connect("activate", self._pause_action)
        self.add_action(pause_action)
        page_action = Gio.SimpleAction.new("show-page", GLib.VariantType.new("s"))
        page_action.connect("activate", self._page_action)
        self.add_action(page_action)
        language_action = Gio.SimpleAction.new("set-language", GLib.VariantType.new("s"))
        language_action.connect("activate", self._language_action)
        self.add_action(language_action)
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", self._quit_action)
        self.add_action(quit_action)
        GLib.timeout_add_seconds(2, self.scheduler.tick)
        GLib.timeout_add_seconds(30, self._theme_schedule_tick)

    def do_activate(self) -> None:
        if self.trigger_kind in REMINDER_META:
            self.scheduler.trigger(self.trigger_kind)
            self.trigger_kind = None
            return
        if self.background and not self.window:
            self.background = False
            return
        if not self.window:
            self.window = MainWindow(self)
        self.window.refresh()
        self.window.present()

    def _load_css(self) -> None:
        stylesheet = (ASSET_ROOT / "style.css").read_text(encoding="utf-8")
        stylesheet = render_palette_css(
            stylesheet,
            str(self.config.data.get("color_theme", "teal")),
        )
        provider = Gtk.CssProvider()
        provider.load_from_data(stylesheet.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display:
            if self._css_provider is not None:
                Gtk.StyleContext.remove_provider_for_display(display, self._css_provider)
            # ~/.config/gtk-4.0/gtk.css is loaded at USER (800).  Custom desktop
            # themes often hard-code their accent there, after application CSS.
            # Use one level above it so Zdorovo's own palette remains local and
            # deterministic without changing the user's system-wide theme.
            Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)
        self._css_provider = provider

    def apply_palette(self) -> None:
        self.config.data["color_theme"] = normalize_color_theme(self.config.data.get("color_theme"))
        self.config.save()
        set_active_color_theme(str(self.config.data["color_theme"]))
        self._load_css()
        if self.window:
            page = self.window.stack.get_visible_child_name() or "settings"
            GLib.idle_add(self.rebuild_window, page)

    def effective_dark_mode(self) -> bool:
        mode = str(self.config.data.get("theme_mode", "light"))
        if mode == "auto":
            return automatic_theme_is_dark(
                light_time=str(self.config.data.get("theme_light_time", "07:00")),
                dark_time=str(self.config.data.get("theme_dark_time", "21:00")),
            )
        return mode == "dark"

    def apply_color_scheme(self) -> None:
        dark = self.effective_dark_mode()
        if bool(self.config.data.get("dark_mode", False)) != dark:
            self.config.data["dark_mode"] = dark
            self.config.save()
        scheme = Adw.ColorScheme.FORCE_DARK if dark else Adw.ColorScheme.FORCE_LIGHT
        Adw.StyleManager.get_default().set_color_scheme(scheme)
        if self.window:
            self.window.apply_theme_state(dark)

    def _theme_schedule_tick(self) -> bool:
        if self.config.data.get("theme_mode") == "auto" and (
            self.effective_dark_mode() != bool(self.config.data.get("dark_mode", False))
        ):
            self.apply_color_scheme()
            if self.window:
                self.window.refresh()
        return GLib.SOURCE_CONTINUE

    def rebuild_window(self, page: str = "today") -> bool:
        old_window = self.window
        width, height, maximized = 1060, 720, False
        if old_window:
            width = max(780, old_window.get_width())
            height = max(560, old_window.get_height())
            maximized = old_window.is_maximized()
            old_window.set_visible(False)
            self.window = None
            old_window.destroy()
        self.window = MainWindow(self)
        self.window.set_default_size(width, height)
        if maximized:
            self.window.maximize()
        if page in (
            "today",
            "breathing",
            "training",
            "habits",
            "achievements",
            "analytics",
            "settings",
            "health",
        ):
            self.window.stack.set_visible_child_name(page)
        self.window.present()
        return GLib.SOURCE_REMOVE

    def set_language(self, language: str, page: str = "settings") -> None:
        if language not in ("en", "ru"):
            return
        self.config.data["language"] = language
        self.config.data["language_selected"] = True
        self.config.save()
        if self.window:
            GLib.idle_add(self.window.reload_language, page)
        else:
            GLib.idle_add(self.rebuild_window, page)

    def _show_reminder(self, payload: dict[str, Any]) -> None:
        if self.overlay:
            self.overlay.destroy()
        self._restore_window_after_overlay = bool(self.window and self.window.get_visible())
        if self.window:
            self.window.set_visible(False)
        self.overlay = FallbackOverlay(self, payload)
        if self.window:
            self.overlay.set_transient_for(self.window)
        self.overlay.connect("destroy", self._overlay_destroyed)
        self.overlay.present()

    def _prompt_wellness(self) -> None:
        if not bool(self.config.data.get("wellness_checkin_enabled", True)) or not bool(
            self.config.data.get("wellness_reminders_enabled", True)
        ):
            return
        language = str(self.config.data.get("language", "en"))
        self.push_app_notification(
            "wellness",
            "How are you feeling today?" if language == "en" else "Как вы себя чувствуете сегодня?",
            (
                "A 20-second check-in helps compare symptoms with screen time and breaks."
                if language == "en"
                else "Короткая отметка поможет сравнить самочувствие с экранным временем и паузами."
            ),
            "today",
            notification_id="wellness-checkin",
            button="Check in" if language == "en" else "Оценить",
        )

    def _prompt_habit(self, habit: dict[str, Any]) -> None:
        language = str(self.config.data.get("language", "en"))
        title = str(habit.get("title") or ("Healthy habit" if language == "en" else "Полезная привычка"))
        title = localized_text(language, title)
        target = max(1, int(habit.get("target", 1)))
        completed = self.db.habit_count(str(habit.get("id") or ""))
        body = (
            f"Today: {completed} of {target}. Mark it when it is genuinely done."
            if language == "en"
            else f"Сегодня: {completed} из {target}. Отметьте только после реального выполнения."
        )
        self.push_app_notification(
            "habit",
            title,
            body,
            "habits",
            notification_id=f"habit-{habit.get('id')}-{datetime.now():%Y-%m-%d}",
            button="Open habits" if language == "en" else "Открыть привычки",
        )

    def _prompt_training(
        self,
        enrollment: sqlite3.Row,
        plan: dict[str, Any],
        repeat_count: int,
    ) -> None:
        language = str(self.config.data.get("language", "en"))
        course = COURSES.get(str(enrollment["course_id"]))
        if not course:
            return
        course_title = training_copy(course, "title", language)
        title = "Workout planned for today" if language == "en" else "Сегодня запланирована тренировка"
        if repeat_count > 1:
            title = "Your workout is still waiting" if language == "en" else "Тренировка ещё ждёт вас"
        body = (
            f"{course_title}: {plan['title']}. Open the plan when you have enough time to complete it without rushing."
            if language == "en"
            else f"{course_title}: {plan['title']}. Откройте план, когда сможете выполнить его спокойно и без спешки."
        )
        self.push_app_notification(
            "training",
            title,
            body,
            "training",
            notification_id=f"training-reminder-{int(enrollment['id'])}-{datetime.now():%Y-%m-%d}",
            button="Open training" if language == "en" else "Открыть тренировку",
        )

    def push_app_notification(
        self,
        kind: str,
        title: str,
        body: str,
        page: str,
        notification_id: str | None = None,
        button: str | None = None,
        system: bool = True,
    ) -> str:
        notification_id = self.db.add_notification(kind, title, body, page, notification_id=notification_id)
        if system:
            notification = Gio.Notification.new(title.strip() or "Zdorovo")
            notification.set_body(body.strip() or title.strip())
            notification.set_icon(Gio.ThemedIcon.new(APP_ICON_NAME))
            notification.set_priority(Gio.NotificationPriority.HIGH)
            target = GLib.Variant("s", page)
            notification.set_default_action_and_target("app.show-page", target)
            if button:
                notification.add_button_with_target(button, "app.show-page", target)
            self.send_notification(notification_id, notification)
        if self.window:
            self.window.refresh(rebuild_lists=False)
        return notification_id

    def _overlay_destroyed(self, overlay: FallbackOverlay) -> None:
        if self.overlay is overlay:
            self.overlay = None
        if self._restore_window_after_overlay and self.window:
            self._restore_window_after_overlay = False
            self.window.present()

    def _scheduler_changed(self) -> None:
        if self.overlay and not self.scheduler.state.get("active_id"):
            self.overlay.destroy()
        now = time.monotonic()
        if now - self._last_achievement_check > 10:
            self._last_achievement_check = now
            self._check_achievements()
        if self.window and self.window.get_visible() and now - self._last_ui_refresh > 5:
            self.window.refresh(rebuild_lists=False)
            self._last_ui_refresh = now

    def _check_achievements(self) -> None:
        unlocked = self.db.evaluate_achievements()
        if not unlocked:
            return
        language = str(self.config.data.get("language", "en"))
        if len(unlocked) == 1:
            achievement = unlocked[0]
            title = "Achievement unlocked" if language == "en" else "Новое достижение"
            body = achievement_unlock_body(achievement, language)
        else:
            title = "New achievements" if language == "en" else "Новые достижения"
            body = (
                f"You unlocked {len(unlocked)} new emblems."
                if language == "en"
                else f"Открыто новых эмблем: {len(unlocked)}."
            )
        self.push_app_notification(
            "achievement",
            title,
            body,
            "achievements",
            notification_id=f"achievement-{int(time.time())}",
            button="View emblems" if language == "en" else "Посмотреть эмблемы",
        )

    def do_shutdown(self) -> None:
        self.scheduler.stop()
        self.db.close()
        Adw.Application.do_shutdown(self)

    def _trigger_action(self, _action: Gio.SimpleAction, parameter: GLib.Variant) -> None:
        kind = parameter.get_string()
        if kind in REMINDER_META:
            self.scheduler.trigger(kind)

    def _respond_action(self, _action: Gio.SimpleAction, parameter: GLib.Variant) -> None:
        action = parameter.get_string()
        reminder_id = self.scheduler.state.get("active_id")
        if reminder_id and action in ("done", "snooze"):
            atomic_json(RESPONSE_FILE, {"id": reminder_id, "action": action, "timestamp": time.time()})

    def _quit_action(self, _action: Gio.SimpleAction, _parameter: GLib.Variant | None) -> None:
        if self.overlay:
            self.overlay.destroy()
            self.overlay = None
        self.quit()

    def _theme_action(self, _action: Gio.SimpleAction, parameter: GLib.Variant) -> None:
        dark = parameter.get_boolean()
        self.config.data["dark_mode"] = dark
        self.config.data["theme_mode"] = "dark" if dark else "light"
        self.config.save()
        self.apply_color_scheme()

    def _pause_action(self, _action: Gio.SimpleAction, parameter: GLib.Variant) -> None:
        self.config.data["manual_pause"] = parameter.get_boolean()
        self.config.save()
        if self.window:
            self.window.refresh()

    def _page_action(self, _action: Gio.SimpleAction, parameter: GLib.Variant) -> None:
        page = parameter.get_string()
        if not self.window:
            self.window = MainWindow(self)
        if page in (
            "today",
            "breathing",
            "training",
            "habits",
            "achievements",
            "analytics",
            "settings",
            "health",
        ):
            self.window.stack.set_visible_child_name(page)
        self.window.present()

    def _language_action(self, _action: Gio.SimpleAction, parameter: GLib.Variant) -> None:
        self.set_language(parameter.get_string(), "settings")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--version", action="version", version=f"Zdorovo {APP_VERSION}")
    parser.add_argument("--background", action="store_true", help="run without opening the window")
    parser.add_argument("--trigger", choices=list(REMINDER_META), help="show a reminder now")
    args, gtk_args = parser.parse_known_args(argv)
    app = ZdorovoApplication(background=args.background, trigger=args.trigger)
    return app.run([sys.argv[0], *gtk_args])


if __name__ == "__main__":
    raise SystemExit(main())
