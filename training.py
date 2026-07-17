"""Training course plans used by the GTK interface and persistence tests."""

from __future__ import annotations

from typing import Any

COURSE_DURATIONS = (7, 30, 180, 360)
DEFAULT_WEEKDAYS: dict[int, tuple[int, ...]] = {
    2: (0, 3),
    3: (0, 2, 4),
    4: (0, 2, 4, 5),
    5: (0, 1, 2, 4, 5),
}

FITNESS_LEVELS: dict[str, dict[str, Any]] = {
    "beginner": {
        "title_en": "Getting started",
        "title_ru": "Начинаю заниматься",
        "short_en": "Starter",
        "short_ru": "Старт",
        "description_en": "One calm round with the base exercise list and the longest recovery.",
        "description_ru": "Один спокойный круг с базовым набором упражнений и самым долгим восстановлением.",
        "factor": 0.8,
        "rest_seconds": 75,
        "round_bonus": 0,
        "round_cap": 1,
        "exercise_bonus": 0,
    },
    "regular": {
        "title_en": "Basic fitness",
        "title_ru": "Базовая подготовка",
        "short_en": "Basic",
        "short_ru": "Базовый",
        "description_en": "The full base list grows from one to two rounds as the course progresses.",
        "description_ru": "Полный базовый комплекс постепенно увеличивается с одного до двух кругов.",
        "factor": 0.95,
        "rest_seconds": 60,
        "round_bonus": 0,
        "round_cap": 2,
        "exercise_bonus": 0,
    },
    "trained": {
        "title_en": "Regular training",
        "title_ru": "Занимаюсь регулярно",
        "short_en": "Regular",
        "short_ru": "Регулярный",
        "description_en": "Two rounds from the start, one extra strength movement and shorter recovery.",
        "description_ru": "Два круга с начала курса, дополнительное силовое упражнение и более короткий отдых.",
        "factor": 1.1,
        "rest_seconds": 50,
        "round_bonus": 1,
        "round_cap": 2,
        "exercise_bonus": 1,
    },
    "advanced": {
        "title_en": "Well trained",
        "title_ru": "Хорошая подготовка",
        "short_en": "Advanced",
        "short_ru": "Продвинутый",
        "description_en": "The highest controlled volume with extra strength movements and up to three rounds.",
        "description_ru": "Наибольший контролируемый объём с дополнительными силовыми упражнениями и тремя кругами.",
        "factor": 1.3,
        "rest_seconds": 45,
        "round_bonus": 2,
        "round_cap": 3,
        "exercise_bonus": 2,
    },
}
FITNESS_LEVEL_ORDER = tuple(FITNESS_LEVELS)


EXERCISES: dict[str, dict[str, Any]] = {
    "room_warmup": {
        "title_en": "Standing room warm-up",
        "title_ru": "Разминка на месте",
        "instruction_en": "Alternate heel digs, gentle shoulder rolls and shallow knee bends without travelling around the room.",
        "instruction_ru": "Чередуйте касания пяткой перед собой, мягкие круги плечами и неглубокие сгибания коленей, оставаясь на месте.",
        "cue_en": "Keep the pace easy and use stable support whenever it feels useful.",
        "cue_ru": "Сохраняйте спокойный темп и при необходимости используйте устойчивую опору.",
        "metric": "minutes",
        "targets": (3, 4, 5, 6),
        "icon": "general",
        "image": "training-room-warmup.png",
    },
    "abdominal_bracing": {
        "title_en": "Abdominal bracing",
        "title_ru": "Мягкое напряжение мышц живота",
        "instruction_en": "Lie on your back with knees bent. Gently tighten the abdomen without holding your breath.",
        "instruction_ru": "Лягте на спину, согнув колени. Мягко напрягите живот, не задерживая дыхание.",
        "cue_en": "Keep the neck relaxed and the movement small.",
        "cue_ru": "Сохраняйте шею расслабленной и не прилагайте чрезмерного усилия.",
        "metric": "seconds",
        "targets": (10, 15, 20, 25),
        "icon": "back",
        "image": "training-abdominal-bracing.png",
    },
    "bird_dog": {
        "title_en": "Supported bird dog",
        "title_ru": "Упрощённая противоположная рука и нога",
        "instruction_en": "From hands and knees, extend one arm or the opposite leg. Combine them only if balance stays easy.",
        "instruction_ru": "Стоя на четвереньках, вытяните одну руку или противоположную ногу. Совмещайте движения только при уверенном равновесии.",
        "cue_en": "Keep the back quiet; a smaller reach is fine.",
        "cue_ru": "Не прогибайтесь; небольшая амплитуда подходит лучше, чем усилие.",
        "metric": "reps_each",
        "targets": (4, 5, 6, 8),
        "icon": "back",
        "image": "training-bird-dog.png",
    },
    "hip_bridge": {
        "title_en": "Hip bridge",
        "title_ru": "Ягодичный мост",
        "instruction_en": "Lie with knees bent, tighten the abdomen and buttocks, then lift the pelvis only as far as comfortable.",
        "instruction_ru": "Лягте с согнутыми коленями, напрягите живот и ягодицы и поднимите таз только до комфортной высоты.",
        "cue_en": "Do not tense the neck or push through pain.",
        "cue_ru": "Не напрягайте шею и не продолжайте через боль.",
        "metric": "reps",
        "targets": (5, 6, 8, 10),
        "icon": "back",
        "image": "training-hip-bridge.png",
    },
    "knee_plank": {
        "title_en": "Plank from the knees",
        "title_ru": "Планка с опорой на колени",
        "instruction_en": "Place forearms under the shoulders and keep the body in one line from shoulders to knees.",
        "instruction_ru": "Поставьте предплечья под плечами и удерживайте прямую линию от плеч до коленей.",
        "cue_en": "Stop before the lower back sags.",
        "cue_ru": "Закончите подход до того, как поясница начнёт провисать.",
        "metric": "seconds",
        "targets": (10, 15, 20, 25),
        "icon": "back",
        "image": "training-knee-plank.png",
    },
    "side_plank_knee": {
        "title_en": "Modified side plank",
        "title_ru": "Боковая планка с согнутой ногой",
        "instruction_en": "Lie on your side with the elbow below the shoulder and the lower knee bent. Lift the hip a little.",
        "instruction_ru": "Лягте на бок, поставьте локоть под плечом и согните нижнюю ногу. Немного поднимите таз.",
        "cue_en": "Keep the neck in line with the spine.",
        "cue_ru": "Сохраняйте шею на одной линии с позвоночником.",
        "metric": "seconds_each",
        "targets": (8, 10, 12, 15),
        "icon": "back",
        "image": "training-side-plank.png",
    },
    "sit_to_stand": {
        "title_en": "Sit to stand",
        "title_ru": "Вставание со стула",
        "instruction_en": "Use a stable chair. Lean forward slightly, stand through the legs, then sit down slowly.",
        "instruction_ru": "Используйте устойчивый стул. Немного наклонитесь вперёд, встаньте за счёт ног и медленно сядьте.",
        "cue_en": "Use hand support if needed and keep the knees comfortable.",
        "cue_ru": "При необходимости опирайтесь руками и сохраняйте комфорт в коленях.",
        "metric": "reps",
        "targets": (5, 6, 8, 10),
        "icon": "general",
        "image": "training-sit-to-stand.png",
    },
    "chair_squat": {
        "title_en": "Chair-guided squat",
        "title_ru": "Приседание до стула",
        "instruction_en": "Stand just in front of a stable chair, send the hips back and bend the knees until the seat is lightly touched, then stand tall.",
        "instruction_ru": "Встаньте перед устойчивым стулом, отведите таз назад и согните колени до лёгкого касания сиденья, затем выпрямитесь.",
        "cue_en": "Keep the heels down and choose a depth that stays comfortable for the knees and back.",
        "cue_ru": "Не отрывайте пятки и выбирайте глубину, комфортную для коленей и спины.",
        "metric": "reps",
        "targets": (5, 7, 9, 12),
        "icon": "general",
        "image": "training-chair-squat.png",
    },
    "supported_split_squat": {
        "title_en": "Supported split squat",
        "title_ru": "Приседание в разножке с опорой",
        "instruction_en": "Take a short split stance beside a stable chair, lower both knees through a small controlled range, then press back up.",
        "instruction_ru": "Встаньте в короткую разножку рядом с устойчивым стулом, немного согните оба колена и плавно вернитесь вверх.",
        "cue_en": "Use the chair lightly, keep the front heel down and shorten the range if balance changes.",
        "cue_ru": "Слегка придерживайтесь за стул, не отрывайте переднюю пятку и уменьшите амплитуду, если теряется равновесие.",
        "metric": "reps_each",
        "targets": (4, 5, 7, 9),
        "icon": "general",
        "image": "training-split-squat.png",
        "min_level": "regular",
    },
    "wall_pushup": {
        "title_en": "Wall press-up",
        "title_ru": "Отжимание от стены",
        "instruction_en": "Place the hands on a wall at chest height, bend the elbows slowly, then press away.",
        "instruction_ru": "Поставьте ладони на стену на уровне груди, медленно согните руки и плавно оттолкнитесь.",
        "cue_en": "Keep the body straight and the shoulders away from the ears.",
        "cue_ru": "Держите корпус ровно, а плечи — подальше от ушей.",
        "metric": "reps",
        "targets": (5, 6, 8, 10),
        "icon": "general",
        "image": "training-wall-pushup.png",
    },
    "floor_pushup": {
        "title_en": "Floor push-up",
        "title_ru": "Отжимание от пола",
        "instruction_en": "Place the hands a little wider than the shoulders, keep the body in one line and lower only as far as control stays steady.",
        "instruction_ru": "Поставьте ладони немного шире плеч, удерживайте корпус одной линией и опускайтесь только до уверенно контролируемой глубины.",
        "cue_en": "Use the knees for support if the lower back or shoulder position starts to change.",
        "cue_ru": "Перейдите на опору коленями, если начинает меняться положение поясницы или плеч.",
        "metric": "reps",
        "targets": (4, 6, 8, 10),
        "icon": "general",
        "image": "training-floor-pushup.png",
        "min_level": "regular",
    },
    "chair_dip": {
        "title_en": "Shallow chair dip",
        "title_ru": "Неглубокое обратное отжимание",
        "instruction_en": "Use a stable chair against a wall. Keep the hips close to the seat and bend the elbows only through a small comfortable range.",
        "instruction_ru": "Поставьте устойчивый стул к стене. Держите таз рядом с сиденьем и сгибайте локти только в небольшой комфортной амплитуде.",
        "cue_en": "Keep the shoulders down and stop immediately for pinching or pain at the front of the shoulder.",
        "cue_ru": "Не поднимайте плечи и сразу остановитесь при защемлении или боли в передней части плеча.",
        "metric": "reps",
        "targets": (4, 5, 6, 8),
        "icon": "general",
        "image": "training-chair-dip.png",
        "min_level": "trained",
    },
    "palm_press": {
        "title_en": "Gentle palm press",
        "title_ru": "Мягкое давление ладонями",
        "instruction_en": "Bring the palms together at chest height and press them gently without lifting the shoulders.",
        "instruction_ru": "Соедините ладони на уровне груди и мягко надавите ими друг на друга, не поднимая плечи.",
        "cue_en": "The effort should stay light and the breathing free.",
        "cue_ru": "Усилие должно оставаться небольшим, а дыхание — свободным.",
        "metric": "seconds",
        "targets": (10, 15, 20, 25),
        "icon": "neck",
        "image": "training-palm-press.png",
    },
    "scapular_set": {
        "title_en": "Shoulder-blade set",
        "title_ru": "Мягкое сведение лопаток",
        "instruction_en": "Stand tall and gently draw the shoulder blades back and down, then release fully.",
        "instruction_ru": "Встаньте ровно, мягко направьте лопатки назад и вниз, затем полностью расслабьтесь.",
        "cue_en": "Do not lift the shoulders or force the range.",
        "cue_ru": "Не поднимайте плечи и не увеличивайте амплитуду силой.",
        "metric": "reps",
        "targets": (6, 8, 10, 12),
        "icon": "neck",
        "image": "training-scapular-set.png",
    },
    "wall_slide": {
        "title_en": "Comfortable wall slide",
        "title_ru": "Скольжение руками по стене",
        "instruction_en": "Rest the forearms on a wall and slide them upward only within a comfortable shoulder range.",
        "instruction_ru": "Поставьте предплечья на стену и скользите ими вверх только в комфортной для плеч амплитуде.",
        "cue_en": "Stop well before pinching, pain or numbness.",
        "cue_ru": "Остановитесь до появления защемления, боли или онемения.",
        "metric": "reps",
        "targets": (5, 6, 8, 10),
        "icon": "neck",
        "image": "training-wall-slide.png",
    },
    "scapular_wall_push": {
        "title_en": "Straight-arm wall press",
        "title_ru": "Жим от стены прямыми руками",
        "instruction_en": "Lean into a wall with straight elbows, let the shoulder blades move gently together, then push the wall away without bending the arms.",
        "instruction_ru": "Обопритесь на стену прямыми руками, мягко сблизьте лопатки, затем оттолкните стену, не сгибая локти.",
        "cue_en": "Keep the body in one line and make the movement only at the shoulder blades.",
        "cue_ru": "Сохраняйте корпус одной линией и двигайтесь только за счёт лопаток.",
        "metric": "reps",
        "targets": (6, 8, 10, 12),
        "icon": "neck",
        "image": "training-scapular-wall.png",
    },
    "prone_w_raise": {
        "title_en": "Prone W raise",
        "title_ru": "Подъём рук буквой W лёжа",
        "instruction_en": "Lie face down with the elbows bent into a W. Lift the forearms slightly while drawing the shoulder blades back and down.",
        "instruction_ru": "Лягте на живот и согните руки буквой W. Слегка поднимите предплечья, направляя лопатки назад и вниз.",
        "cue_en": "Keep the neck long, the lift small and the lower back relaxed.",
        "cue_ru": "Вытягивайте шею, поднимайте руки невысоко и не напрягайте поясницу.",
        "metric": "reps",
        "targets": (5, 7, 9, 12),
        "icon": "back",
        "image": "training-prone-w.png",
    },
    "supine_heel_slide": {
        "title_en": "Supine heel slide",
        "title_ru": "Скольжение пяткой лёжа",
        "instruction_en": "Lie on your back with both knees bent. Slowly slide one heel away, stop before the lower back changes, then return and alternate sides.",
        "instruction_ru": "Лягте на спину, согнув колени. Медленно отведите одну пятку, остановитесь до изменения положения поясницы и вернитесь, затем смените ногу.",
        "cue_en": "Breathe freely and use a shorter slide if the abdomen loses gentle tension.",
        "cue_ru": "Дышите свободно и уменьшите движение, если живот перестаёт сохранять мягкое напряжение.",
        "metric": "reps_each",
        "targets": (4, 6, 8, 10),
        "icon": "back",
        "image": "training-heel-slide.png",
    },
    "calf_raise": {
        "title_en": "Supported calf raise",
        "title_ru": "Подъём на носки с опорой",
        "instruction_en": "Hold a stable chair or wall, rise onto the toes slowly and lower with control.",
        "instruction_ru": "Держитесь за устойчивый стул или стену, медленно поднимитесь на носки и плавно опуститесь.",
        "cue_en": "Keep an easy grip on the support.",
        "cue_ru": "Не переносите весь вес на руки.",
        "metric": "reps",
        "targets": (6, 8, 10, 12),
        "icon": "general",
        "image": "training-calf-raise.png",
    },
    "side_leg_raise": {
        "title_en": "Supported side leg raise",
        "title_ru": "Отведение ноги в сторону с опорой",
        "instruction_en": "Hold stable support and lift one straight leg slightly to the side without leaning the body.",
        "instruction_ru": "Держитесь за устойчивую опору и немного отведите прямую ногу в сторону, не наклоняя корпус.",
        "cue_en": "A small controlled movement is enough.",
        "cue_ru": "Достаточно небольшой контролируемой амплитуды.",
        "metric": "reps_each",
        "targets": (4, 5, 6, 8),
        "icon": "general",
        "image": "training-side-leg-raise.png",
    },
    "hamstring_curl": {
        "title_en": "Supported hamstring curl",
        "title_ru": "Сгибание ноги стоя с опорой",
        "instruction_en": "Hold a stable chair, keep the thighs beside each other and bend one knee to bring the heel upward, then lower slowly.",
        "instruction_ru": "Держитесь за устойчивый стул, сохраняйте бёдра рядом и согните одно колено, поднимая пятку, затем медленно опустите ногу.",
        "cue_en": "Stay tall and stop before the pelvis tilts or the lower back arches.",
        "cue_ru": "Сохраняйте ровный корпус и остановитесь до наклона таза или прогиба в пояснице.",
        "metric": "reps_each",
        "targets": (5, 7, 9, 12),
        "icon": "general",
        "image": "training-hamstring-curl.png",
    },
    "hip_hinge_wall": {
        "title_en": "Hip hinge to a wall",
        "title_ru": "Отведение таза к стене",
        "instruction_en": "Stand a short step from a wall and move the hips backward until they touch it, then stand tall.",
        "instruction_ru": "Встаньте в небольшом шаге от стены, отведите таз назад до касания и снова выпрямитесь.",
        "cue_en": "Keep the movement at the hips and the back comfortable.",
        "cue_ru": "Двигайтесь в тазобедренных суставах, сохраняя комфорт в спине.",
        "metric": "reps",
        "targets": (5, 6, 8, 10),
        "icon": "back",
        "image": "training-hip-hinge.png",
    },
    "knee_lifts": {
        "title_en": "Supported knee lifts",
        "title_ru": "Подъёмы коленей с опорой",
        "instruction_en": "Hold stable support if useful and alternate lifting each knee only as high as comfortable.",
        "instruction_ru": "При необходимости держитесь за устойчивую опору и поочерёдно поднимайте колени только до комфортной высоты.",
        "cue_en": "Stay tall, keep the movement controlled and place each foot down quietly.",
        "cue_ru": "Сохраняйте ровный корпус, двигайтесь подконтрольно и мягко ставьте стопу на пол.",
        "metric": "seconds",
        "targets": (30, 40, 50, 60),
        "icon": "general",
        "image": "training-knee-lifts.png",
    },
    "balance_shift": {
        "title_en": "Supported weight shift",
        "title_ru": "Перенос веса с опорой",
        "instruction_en": "Stand by stable support and slowly move the weight from one foot to the other.",
        "instruction_ru": "Встаньте рядом с устойчивой опорой и медленно переносите вес с одной стопы на другую.",
        "cue_en": "Keep both feet available for support.",
        "cue_ru": "Обе стопы должны оставаться доступными для опоры.",
        "metric": "reps_each",
        "targets": (4, 5, 6, 8),
        "icon": "general",
        "image": "training-balance-shift.png",
    },
    "mobility_reset": {
        "title_en": "Easy mobility reset",
        "title_ru": "Спокойная смена движений",
        "instruction_en": "Alternate comfortable shoulder-blade movements, ankle circles and gentle heel taps in place.",
        "instruction_ru": "Чередуйте комфортные движения лопаток, круги стопами и мягкие касания пяткой перед собой.",
        "cue_en": "This is recovery, not a flexibility test.",
        "cue_ru": "Это восстановление, а не проверка гибкости.",
        "metric": "minutes",
        "targets": (4, 5, 6, 8),
        "icon": "general",
        "image": "training-mobility-reset.png",
    },
}


COURSE_ALIASES = {
    "core": "full_body",
    "shoulders": "upper_body",
    "back": "upper_body",
}


def normalize_course_id(course_id: str) -> str:
    """Map course identifiers from older releases to the current catalogue."""
    return COURSE_ALIASES.get(str(course_id), str(course_id))


COURSES: dict[str, dict[str, Any]] = {
    "full_body": {
        "title_en": "Full-body strength",
        "title_ru": "Всё тело",
        "subtitle_en": "Every major muscle group in one balanced plan",
        "subtitle_ru": "Все основные группы мышц в одном сбалансированном плане",
        "description_en": "Combine a squat pattern, pushing, upper-back control, hip work and trunk stability across two alternating sessions.",
        "description_ru": "Чередуйте приседания, жимовые движения, работу верхней части спины, таза и мышц корпуса в двух разных тренировках.",
        "equipment_en": "Stable chair, wall and mat",
        "equipment_ru": "Устойчивый стул, стена и коврик",
        "icon": "general",
        "image": "training-chair-squat.png",
        "a": (
            "room_warmup",
            "chair_squat",
            "wall_pushup",
            "hip_bridge",
            "prone_w_raise",
            "supine_heel_slide",
        ),
        "b": (
            "room_warmup",
            "sit_to_stand",
            "scapular_wall_push",
            "bird_dog",
            "calf_raise",
            "floor_pushup",
        ),
    },
    "upper_body": {
        "title_en": "Arms, shoulders and back",
        "title_ru": "Руки, плечи и спина",
        "subtitle_en": "Push, shoulder-blade and upper-back strength",
        "subtitle_ru": "Жимовые движения, контроль лопаток и сила верхней части спины",
        "description_en": "Progress from wall work to floor press-ups while balancing it with straight-arm shoulder-blade control and prone back work.",
        "description_ru": "Переходите от работы у стены к отжиманиям от пола, сохраняя баланс за счёт контроля лопаток и упражнений для спины лёжа.",
        "equipment_en": "Wall, mat and stable chair",
        "equipment_ru": "Стена, коврик и устойчивый стул",
        "icon": "neck",
        "image": "training-prone-w.png",
        "a": (
            "room_warmup",
            "scapular_set",
            "wall_pushup",
            "prone_w_raise",
            "palm_press",
            "chair_dip",
        ),
        "b": (
            "room_warmup",
            "wall_slide",
            "scapular_wall_push",
            "prone_w_raise",
            "floor_pushup",
            "bird_dog",
        ),
    },
    "legs": {
        "title_en": "Legs and stability",
        "title_ru": "Ноги и устойчивость",
        "subtitle_en": "Everyday strength with stable support",
        "subtitle_ru": "Сила для повседневных движений рядом с опорой",
        "description_en": "Build a comfortable base for standing, controlled leg movement and calf strength with a chair nearby.",
        "description_ru": "Создавайте комфортную базу для вставания, контролируемых движений ног и работы голеней рядом с устойчивым стулом.",
        "equipment_en": "Stable chair or wall",
        "equipment_ru": "Устойчивый стул или стена",
        "icon": "general",
        "image": "training-calf-raise.png",
        "a": ("room_warmup", "sit_to_stand", "calf_raise", "knee_lifts"),
        "b": ("room_warmup", "side_leg_raise", "hip_hinge_wall", "balance_shift"),
    },
    "lower_body": {
        "title_en": "Leg strength",
        "title_ru": "Сила ног",
        "subtitle_en": "A stronger squat, hips and posterior chain",
        "subtitle_ru": "Больше силовой работы для приседания, таза и задней поверхности ног",
        "description_en": "Build lower-body strength with chair-guided squats, bridges, supported split squats and controlled hamstring work.",
        "description_ru": "Развивайте силу ног с приседаниями до стула, ягодичным мостом, разножкой с опорой и сгибанием голени.",
        "equipment_en": "Stable chair and mat",
        "equipment_ru": "Устойчивый стул и коврик",
        "icon": "general",
        "image": "training-split-squat.png",
        "a": (
            "room_warmup",
            "chair_squat",
            "hip_bridge",
            "calf_raise",
            "hamstring_curl",
            "supported_split_squat",
        ),
        "b": (
            "room_warmup",
            "sit_to_stand",
            "hip_hinge_wall",
            "side_leg_raise",
            "hamstring_curl",
            "supported_split_squat",
        ),
    },
    "balance": {
        "title_en": "Mobility and balance",
        "title_ru": "Подвижность и баланс",
        "subtitle_en": "Steady movement with reliable support",
        "subtitle_ru": "Уверенные движения рядом с опорой",
        "description_en": "Practice weight shifts, leg strength and controlled movement without unsupported balance challenges.",
        "description_ru": "Тренируйте перенос веса, силу ног и контролируемые движения без сложных упражнений на равновесие без опоры.",
        "equipment_en": "Stable chair or wall",
        "equipment_ru": "Устойчивый стул или стена",
        "icon": "general",
        "image": "training-balance-shift.png",
        "a": ("room_warmup", "balance_shift", "calf_raise", "knee_lifts"),
        "b": ("room_warmup", "side_leg_raise", "sit_to_stand", "balance_shift"),
    },
}


def copy(item: dict[str, Any], key: str, language: str) -> str:
    suffix = "en" if language == "en" else "ru"
    return str(item[f"{key}_{suffix}"])


def training_phase(course_day: int, total_days: int) -> tuple[int, bool]:
    """Return a capped progression stage and whether this is a lighter week."""
    day = max(1, min(int(course_day), max(1, int(total_days))))
    if day <= 7:
        stage = 0
    elif day <= 21:
        stage = 1
    elif day <= 60:
        stage = 2
    else:
        stage = 3
    lighter = day > 21 and ((day - 1) // 7 + 1) % 4 == 0
    return (max(1, stage - 1) if lighter else stage), lighter


def target_text(exercise: dict[str, Any], target: int, language: str) -> str:
    metric = str(exercise["metric"])
    if language == "en":
        labels = {
            "reps": f"{target} reps",
            "reps_each": f"{target} each side",
            "seconds": f"{target} sec",
            "seconds_each": f"{target} sec each side",
            "minutes": f"{target} min",
        }
    else:
        labels = {
            "reps": f"{target} повторов",
            "reps_each": f"по {target} на сторону",
            "seconds": f"{target} сек",
            "seconds_each": f"по {target} сек на сторону",
            "minutes": f"{target} мин",
        }
    return labels[metric]


def _estimated_seconds(exercise: dict[str, Any], target: int) -> int:
    metric = str(exercise["metric"])
    if metric == "minutes":
        return target * 60
    if metric == "seconds":
        return target
    if metric == "seconds_each":
        return target * 2
    if metric == "reps_each":
        return target * 8
    return target * 4


def _scaled_target(
    exercise: dict[str, Any],
    phase: int,
    fitness_level: str,
    build_step: int = 0,
) -> int:
    level = FITNESS_LEVELS.get(fitness_level)
    if level is None:
        raise ValueError(f"unsupported fitness level: {fitness_level}")
    base = int(exercise["targets"][phase])
    scaled = int(round(base * float(level["factor"]))) + max(0, int(build_step))
    minimum = 2 if exercise["metric"] == "minutes" else 4
    return max(minimum, scaled)


def strength_build_step(
    course_day: int,
    days_per_week: int,
    weekdays: Any = None,
    start_weekday: int = 0,
) -> int:
    """Count earlier strength sessions in the current three-week build block."""
    selected = normalize_weekdays(weekdays, days_per_week)
    day = max(1, int(course_day))
    week = (day - 1) // 7
    if week % 4 == 3:
        return 0
    block_start = (week // 4) * 28 + 1
    completed_strength = 0
    for previous_day in range(block_start, day):
        previous_week = (previous_day - 1) // 7
        previous_slot = (previous_day - 1) % 7
        kind, _session = weekly_pattern(
            len(selected),
            previous_week,
            selected,
            start_weekday,
        )[previous_slot]
        if kind == "strength":
            completed_strength += 1
    return completed_strength


def normalize_weekdays(
    weekdays: Any = None,
    days_per_week: int = 3,
) -> tuple[int, ...]:
    """Return two to five unique weekday indexes, Monday=0."""
    if weekdays is None:
        if int(days_per_week) not in DEFAULT_WEEKDAYS:
            raise ValueError(f"unsupported training days: {days_per_week}")
        return DEFAULT_WEEKDAYS[int(days_per_week)]
    if isinstance(weekdays, str):
        weekdays = weekdays.split(",")
    try:
        selected = tuple(sorted({int(day) for day in weekdays}))
    except (TypeError, ValueError):
        raise ValueError("invalid training weekdays") from None
    if len(selected) not in (2, 3, 4, 5) or any(day < 0 or day > 6 for day in selected):
        raise ValueError("training weekdays must contain two to five days")
    return selected


def weekly_pattern(
    days_per_week: int,
    week: int = 0,
    weekdays: Any = None,
    start_weekday: int = 0,
) -> tuple[tuple[str, str], ...]:
    """Return a seven-day rhythm beginning at ``start_weekday``."""
    selected = normalize_weekdays(weekdays, days_per_week)
    if not 0 <= int(start_weekday) <= 6:
        raise ValueError(f"unsupported start weekday: {start_weekday}")
    third_strength = ("strength", "a" if week % 2 == 0 else "b")
    roles: dict[int, tuple[str, str]]
    if len(selected) == 2:
        sequence = (("strength", "a"), ("strength", "b"))
    elif len(selected) == 3:
        sequence = (("strength", "a"), ("strength", "b"), third_strength)
    elif len(selected) == 4:
        sequence = (
            ("strength", "a"),
            ("strength", "b"),
            third_strength,
            ("mobility", "mobility"),
        )
    else:
        sequence = (
            ("strength", "a"),
            ("recovery", "recovery"),
            ("strength", "b"),
            ("mobility", "mobility"),
            third_strength,
        )
    roles = dict(zip(selected, sequence, strict=True))
    return tuple(roles.get((int(start_weekday) + offset) % 7, ("rest", "rest")) for offset in range(7))


def training_day(
    course_id: str,
    course_day: int,
    total_days: int,
    language: str = "en",
    fitness_level: str = "beginner",
    days_per_week: int = 3,
    weekdays: Any = None,
    start_weekday: int = 0,
) -> dict[str, Any]:
    course_id = normalize_course_id(course_id)
    if course_id not in COURSES:
        raise ValueError(f"unknown course: {course_id}")
    if int(total_days) not in COURSE_DURATIONS:
        raise ValueError(f"unsupported duration: {total_days}")
    if fitness_level not in FITNESS_LEVELS:
        raise ValueError(f"unsupported fitness level: {fitness_level}")
    selected_weekdays = normalize_weekdays(weekdays, days_per_week)
    course = COURSES[course_id]
    day = max(1, min(int(course_day), int(total_days)))
    slot = (day - 1) % 7
    week = (day - 1) // 7
    phase, lighter = training_phase(day, total_days)
    kind, session_key = weekly_pattern(
        len(selected_weekdays),
        week,
        selected_weekdays,
        start_weekday,
    )[slot]
    build_step = (
        strength_build_step(day, len(selected_weekdays), selected_weekdays, start_weekday)
        if kind == "strength" and not lighter
        else 0
    )

    if kind == "strength":
        exercise_ids = tuple(course[session_key])
        exercise_bonus = int(FITNESS_LEVELS[fitness_level]["exercise_bonus"])
        if exercise_bonus:
            alternate_key = "b" if session_key == "a" else "a"
            extras = tuple(
                exercise_id
                for exercise_id in course[alternate_key]
                if exercise_id not in exercise_ids and exercise_id != "room_warmup"
            )
            exercise_ids += extras[:exercise_bonus]
        level_rank = FITNESS_LEVEL_ORDER.index(fitness_level)
        exercise_ids = tuple(
            exercise_id
            for exercise_id in exercise_ids
            if FITNESS_LEVEL_ORDER.index(EXERCISES[exercise_id].get("min_level", "beginner")) <= level_rank
        )
        title = (
            f"Strength session {session_key.upper()}"
            if language == "en"
            else f"Силовая тренировка {session_key.upper()}"
        )
        description = (
            "Work at a controlled pace and leave several comfortable repetitions in reserve."
            if language == "en"
            else "Двигайтесь подконтрольно и заканчивайте каждый подход с запасом в несколько комфортных повторов."
        )
    elif kind == "recovery":
        exercise_ids = ("room_warmup", "mobility_reset")
        title = "Recovery day" if language == "en" else "День восстановления"
        description = (
            "No planned strength work today. Easy movement supports recovery between sessions."
            if language == "en"
            else "Сегодня без плановой силовой нагрузки. Спокойное движение помогает восстановиться между тренировками."
        )
    elif kind == "mobility":
        exercise_ids = ("room_warmup", "balance_shift", "scapular_set")
        title = "Mobility day" if language == "en" else "День подвижности"
        description = (
            "A short easy session keeps the week varied without adding another hard day."
            if language == "en"
            else "Короткий спокойный комплекс добавляет разнообразие без ещё одного тяжёлого дня."
        )
    else:
        exercise_ids = ()
        title = "Rest day" if language == "en" else "День отдыха"
        description = (
            "Rest from planned exercise. Ordinary comfortable movement is enough."
            if language == "en"
            else "Отдохните от плановых упражнений. Обычной комфортной активности сегодня достаточно."
        )

    base_rounds = 1 if phase < 2 or kind != "strength" else 2
    if kind != "strength":
        rounds = 1
    else:
        rounds = min(
            int(FITNESS_LEVELS[fitness_level]["round_cap"]),
            base_rounds + int(FITNESS_LEVELS[fitness_level]["round_bonus"]),
        )
        if lighter:
            rounds = max(1, rounds - 1)
    exercises: list[dict[str, Any]] = []
    estimated_seconds = 0
    for exercise_id in exercise_ids:
        exercise = EXERCISES[exercise_id]
        target = _scaled_target(
            exercise,
            phase,
            fitness_level,
            build_step if kind == "strength" and exercise_id != "room_warmup" else 0,
        )
        exercises.append(
            {
                "id": exercise_id,
                "title": copy(exercise, "title", language),
                "instruction": copy(exercise, "instruction", language),
                "cue": copy(exercise, "cue", language),
                "target": target_text(exercise, target, language),
                "target_value": target,
                "metric": exercise["metric"],
                "work_seconds": _estimated_seconds(exercise, target),
                "icon": exercise["icon"],
                "image": exercise["image"],
            }
        )
        estimated_seconds += _estimated_seconds(exercise, target) * rounds
    rest_seconds = int(FITNESS_LEVELS[fitness_level]["rest_seconds"])
    final_rest_seconds = 60
    if kind == "rest":
        estimated_seconds = 0
    elif exercises:
        estimated_seconds += max(0, len(exercises) * rounds - 1) * rest_seconds
        estimated_seconds += final_rest_seconds + 5

    phase_names = (
        ("Start", "Base", "Build", "Maintain")
        if language == "en"
        else ("Старт", "База", "Развитие", "Поддержание")
    )
    return {
        "course_id": course_id,
        "course_day": day,
        "total_days": int(total_days),
        "kind": kind,
        "session_key": session_key or kind,
        "title": title,
        "description": description,
        "phase": phase,
        "phase_name": phase_names[phase],
        "lighter": lighter,
        "build_step": build_step,
        "rounds": rounds,
        "fitness_level": fitness_level,
        "fitness_title": copy(FITNESS_LEVELS[fitness_level], "title", language),
        "days_per_week": len(selected_weekdays),
        "weekdays": selected_weekdays,
        "start_weekday": int(start_weekday),
        "rest_seconds": rest_seconds,
        "final_rest_seconds": final_rest_seconds,
        "exercises": exercises,
        "estimated_seconds": estimated_seconds,
    }


def upcoming_days(
    course_id: str,
    course_day: int,
    total_days: int,
    language: str = "en",
    limit: int = 7,
    fitness_level: str = "beginner",
    days_per_week: int = 3,
    weekdays: Any = None,
    start_weekday: int = 0,
) -> list[dict[str, Any]]:
    end = min(int(total_days), int(course_day) + max(1, int(limit)) - 1)
    return [
        training_day(
            course_id,
            day,
            total_days,
            language,
            fitness_level,
            days_per_week,
            weekdays,
            start_weekday,
        )
        for day in range(int(course_day), end + 1)
    ]


def training_stages(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand a course day into exercises, automatic rests and a final recovery."""
    exercises = list(plan.get("exercises", []))
    rounds = max(1, int(plan.get("rounds", 1)))
    flattened: list[dict[str, Any]] = []
    for round_number in range(1, rounds + 1):
        for exercise in exercises:
            metric = str(exercise["metric"])
            value = max(1, int(exercise["target_value"]))
            if metric == "minutes":
                duration_seconds: int | None = value * 60
            elif metric == "seconds":
                duration_seconds = value
            elif metric == "seconds_each":
                duration_seconds = value * 2
            else:
                duration_seconds = None
            flattened.append(
                {
                    "type": "exercise",
                    "round": round_number,
                    "rounds": rounds,
                    "timed": duration_seconds is not None,
                    "duration_seconds": duration_seconds,
                    **exercise,
                }
            )
    stages: list[dict[str, Any]] = []
    for index, exercise in enumerate(flattened):
        stages.append(exercise)
        if index < len(flattened) - 1:
            stages.append(
                {
                    "type": "rest",
                    "duration_seconds": max(15, int(plan.get("rest_seconds", 50))),
                    "next_title": flattened[index + 1]["title"],
                    "next_image": flattened[index + 1]["image"],
                    "next_target": flattened[index + 1]["target"],
                }
            )
    if flattened:
        stages.append(
            {
                "type": "recovery",
                "duration_seconds": max(30, int(plan.get("final_rest_seconds", 60))),
            }
        )
    return stages
