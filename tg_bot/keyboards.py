from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ── Main menu (action-first) ────────────────────────────

def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Мой день", callback_data="skill_my_day"),
    )
    builder.row(
        InlineKeyboardButton(text="📝 Записать", callback_data="log_manual"),
        InlineKeyboardButton(text="📊 Прогресс", callback_data="show_progress"),
    )
    builder.row(
        InlineKeyboardButton(text="🏋️ Программа", callback_data="skill_workout_week"),
        InlineKeyboardButton(text="🍽 Рацион", callback_data="skill_meal_week"),
    )
    builder.row(
        InlineKeyboardButton(text="🍽 Ситуация", callback_data="situ_menu"),
        InlineKeyboardButton(text="💬 Вопрос", callback_data="ask_question"),
    )
    builder.row(
        InlineKeyboardButton(text="📹 Видео", callback_data="menu_video"),
        InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile"),
    )
    return builder.as_markup()


# ── After-skill keyboard ────────────────────────────────

def after_skill_kb(
    repeat_callback: str, repeat_label: str, message_db_id: str | None = None
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if message_db_id:
        short_id = message_db_id.replace("-", "")
        builder.row(
            InlineKeyboardButton(text="👍 Полезно", callback_data=f"fb_up_{short_id}"),
            InlineKeyboardButton(text="👎 Не то", callback_data=f"fb_down_{short_id}"),
        )
    builder.row(
        InlineKeyboardButton(text=repeat_label, callback_data=repeat_callback),
        InlineKeyboardButton(text="◀️ Меню", callback_data="menu_back"),
    )
    return builder.as_markup()


def after_ask_kb(repeat_callback: str, message_db_id: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if message_db_id:
        short_id = message_db_id.replace("-", "")
        builder.row(
            InlineKeyboardButton(text="👍 Полезно", callback_data=f"fb_up_{short_id}"),
            InlineKeyboardButton(text="👎 Не то", callback_data=f"fb_down_{short_id}"),
        )
    builder.row(
        InlineKeyboardButton(text="💬 Ещё вопрос", callback_data=repeat_callback),
        InlineKeyboardButton(text="◀️ Меню", callback_data="menu_back"),
    )
    return builder.as_markup()


# ── Settings ─────────────────────────────────────────────

def settings_kb(current_mode: str = "auto") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Новый диалог", callback_data="reset_conversation"),
    )
    modes = [
        ("🏋️ Тренер", "mode_trainer"),
        ("🥗 Нутрициолог", "mode_dietologist"),
        ("🏛 Авто", "mode_auto"),
    ]
    buttons = []
    for label, data in modes:
        m = data.replace("mode_", "")
        mark = " ✓" if m == current_mode else ""
        buttons.append(InlineKeyboardButton(text=f"{label}{mark}", callback_data=data))
    builder.row(*buttons)
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back"),
    )
    return builder.as_markup()


# ── Quick onboarding keyboards ──────────────────────────

def goal_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔥 Похудеть", callback_data="goal_weight_loss"),
        InlineKeyboardButton(text="💪 Набрать массу", callback_data="goal_muscle_gain"),
    )
    builder.row(
        InlineKeyboardButton(text="🏃 Быть в форме", callback_data="goal_maintenance"),
        InlineKeyboardButton(text="🏆 Стать сильнее", callback_data="goal_strength"),
    )
    return builder.as_markup()


GOAL_LABELS = {
    "weight_loss": "Похудение",
    "muscle_gain": "Набор массы",
    "maintenance": "Поддержание формы",
    "strength": "Сила и выносливость",
}


def fitness_level_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🌱 Новичок", callback_data="fitness_beginner"),
        InlineKeyboardButton(text="⚡ Средний", callback_data="fitness_intermediate"),
    )
    builder.row(
        InlineKeyboardButton(text="🔥 Продвинутый", callback_data="fitness_advanced"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="onboard_back_goal"))
    return builder.as_markup()


FITNESS_LABELS = {
    "beginner": "Новичок",
    "intermediate": "Средний",
    "advanced": "Продвинутый",
}


def gender_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="♂ Мужской", callback_data="gender_male"),
        InlineKeyboardButton(text="♀ Женский", callback_data="gender_female"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="onboard_back_fitness"))
    return builder.as_markup()


# ── Training style keyboard ────────────────────────────

def training_style_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏋️ Зал", callback_data="style_gym"),
        InlineKeyboardButton(text="🏠 Дома", callback_data="style_home"),
    )
    builder.row(
        InlineKeyboardButton(text="🤸 Кроссфит", callback_data="style_crossfit"),
        InlineKeyboardButton(text="🏃 Бег / Йога", callback_data="style_running"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="onboard_back_gender"))
    return builder.as_markup()


TRAINING_STYLE_LABELS = {
    "gym": "Зал",
    "home": "Дома",
    "crossfit": "Кроссфит",
    "running": "Бег / Йога",
}


# ── Activity level keyboard ───────────────────────────

def activity_level_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🛋 1-2 раза/нед", callback_data="activity_sedentary"),
        InlineKeyboardButton(text="🚶 3 раза/нед", callback_data="activity_light"),
    )
    builder.row(
        InlineKeyboardButton(text="🏃 4-5 раз/нед", callback_data="activity_moderate"),
        InlineKeyboardButton(text="🔥 6-7 раз/нед", callback_data="activity_active"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="onboard_back_style"))
    return builder.as_markup()


ACTIVITY_LABELS = {
    "sedentary": "1-2 тренировки в неделю",
    "light": "3 тренировки в неделю",
    "moderate": "4-5 тренировок в неделю",
    "active": "6-7 тренировок в неделю",
}


# ── Training days keyboard ──────────────────────────

def training_days_kb(with_back: bool = False) -> InlineKeyboardMarkup:
    """Pick which days of the week to train. Preset options."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Пн, Ср, Пт", callback_data="days_1,3,5"),
        InlineKeyboardButton(text="Вт, Чт, Сб", callback_data="days_2,4,6"),
    )
    builder.row(
        InlineKeyboardButton(text="Пн, Вт, Чт, Пт", callback_data="days_1,2,4,5"),
    )
    builder.row(
        InlineKeyboardButton(text="Пн, Ср, Пт, Сб", callback_data="days_1,3,5,6"),
    )
    builder.row(
        InlineKeyboardButton(text="Каждый день кроме Вс", callback_data="days_1,2,3,4,5,6"),
    )
    builder.row(
        InlineKeyboardButton(text="Каждый день", callback_data="days_1,2,3,4,5,6,7"),
    )
    if with_back:
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="onboard_back_activity"))
    return builder.as_markup()


TRAINING_DAYS_LABELS = {
    "1,3,5": "Пн, Ср, Пт",
    "2,4,6": "Вт, Чт, Сб",
    "1,2,4,5": "Пн, Вт, Чт, Пт",
    "1,3,5,6": "Пн, Ср, Пт, Сб",
    "1,2,3,4,5,6": "Пн-Сб",
    "1,2,3,4,5,6,7": "Каждый день",
}


# ── Edit profile keyboard ────────────────────────────────

def edit_profile_kb() -> InlineKeyboardMarkup:
    """Fields the user can edit from profile screen."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎯 Цель", callback_data="edit_goal"),
        InlineKeyboardButton(text="💪 Уровень", callback_data="edit_fitness_level"),
    )
    builder.row(
        InlineKeyboardButton(text="🏋️ Стиль", callback_data="edit_training_style"),
        InlineKeyboardButton(text="🏃 Активность", callback_data="edit_activity_level"),
    )
    builder.row(
        InlineKeyboardButton(text="📏 Рост", callback_data="edit_height_cm"),
        InlineKeyboardButton(text="⚖️ Вес", callback_data="edit_weight_kg"),
    )
    builder.row(
        InlineKeyboardButton(text="📅 Дни тренировок", callback_data="edit_training_days"),
    )
    builder.row(
        InlineKeyboardButton(text="🍽 Ограничения питания", callback_data="edit_dietary_restrictions"),
    )
    builder.row(
        InlineKeyboardButton(text="🤧 Аллергии", callback_data="edit_allergies"),
        InlineKeyboardButton(text="⚠️ Травмы", callback_data="edit_limitations"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="menu_profile"),
    )
    return builder.as_markup()


# ── Exercise name keyboard ───────────────────────────────

def exercise_name_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Приседания", callback_data="exercise_squats"),
        InlineKeyboardButton(text="Жим лёжа", callback_data="exercise_bench_press"),
    )
    builder.row(
        InlineKeyboardButton(text="Становая тяга", callback_data="exercise_deadlift"),
        InlineKeyboardButton(text="Подтягивания", callback_data="exercise_pullups"),
    )
    builder.row(
        InlineKeyboardButton(text="Выпады", callback_data="exercise_lunges"),
        InlineKeyboardButton(text="Жим стоя", callback_data="exercise_overhead_press"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel_state"),
    )
    return builder.as_markup()


EXERCISE_LABELS = {
    "squats": "Приседания",
    "bench_press": "Жим лёжа",
    "deadlift": "Становая тяга",
    "pullups": "Подтягивания",
    "lunges": "Выпады",
    "overhead_press": "Жим стоя",
}


# ── Session complete/skip keyboard ──────────────────────

def session_action_kb(session_id: str) -> InlineKeyboardMarkup:
    """Show after today's workout: complete or skip."""
    # UUID without dashes = 32 chars, prefix ~13 chars = ~45 total (fits 64 byte limit)
    sid = session_id.replace("-", "")
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Выполнил", callback_data=f"session_done_{sid}"),
        InlineKeyboardButton(text="⏭ Пропустил", callback_data=f"session_skip_{sid}"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Меню", callback_data="menu_back"),
    )
    return builder.as_markup()


def difficulty_kb(session_id: str) -> InlineKeyboardMarkup:
    """Rate workout difficulty after completion."""
    sid = session_id.replace("-", "")
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1 😴", callback_data=f"diff_{sid}_1"),
        InlineKeyboardButton(text="2 🙂", callback_data=f"diff_{sid}_2"),
        InlineKeyboardButton(text="3 💪", callback_data=f"diff_{sid}_3"),
        InlineKeyboardButton(text="4 🔥", callback_data=f"diff_{sid}_4"),
        InlineKeyboardButton(text="5 🤯", callback_data=f"diff_{sid}_5"),
    )
    return builder.as_markup()


# ── Micro Workout ────────────────────────────────────────

def micro_workout_offer_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🚀 Поехали!", callback_data="micro_start"),
        InlineKeyboardButton(text="⏭ Потом", callback_data="micro_skip"),
    )
    return builder.as_markup()


def micro_exercise_done_kb(exercise_index: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Сделал(а)!", callback_data=f"micro_done_{exercise_index}"),
    )
    builder.row(
        InlineKeyboardButton(text="⏭ Пропустить разминку", callback_data="micro_skip"),
    )
    return builder.as_markup()


# ── Daily reminder keyboard ─────────────────────────────

def daily_reminder_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Мой день", callback_data="skill_my_day"),
    )
    return builder.as_markup()


# ── Cancel keyboard (for stateful flows) ─────────────────

def cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="◀️ Отмена", callback_data="cancel_state"),
    )
    return builder.as_markup()


def skip_or_cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⏭ Пропустить", callback_data="cancel_state"),
        InlineKeyboardButton(text="◀️ Меню", callback_data="menu_back"),
    )
    return builder.as_markup()


# ── Profile ──────────────────────────────────────────────

def profile_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ Изменить", callback_data="edit_profile"),
    )
    builder.row(
        InlineKeyboardButton(text="◀️ Меню", callback_data="menu_back"),
    )
    return builder.as_markup()


# ── Try question (onboarding aha moment) ───────────────

def try_question_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💪 Как накачать грудь?", callback_data="try_q_chest"))
    builder.row(InlineKeyboardButton(text="🍽 Что есть до тренировки?", callback_data="try_q_meal"))
    builder.row(InlineKeyboardButton(text="🏃 С чего начать бегать?", callback_data="try_q_run"))
    builder.row(InlineKeyboardButton(text="💬 Свой вопрос", callback_data="try_q_custom"))
    return builder.as_markup()


def after_try_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🚀 Настроить под меня", callback_data="onboard_start"))
    builder.row(InlineKeyboardButton(text="💬 Ещё вопрос", callback_data="try_q_custom"))
    return builder.as_markup()


# ── Week template (onboarding step 2/2) ───────────────

def week_template_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🏋️ Зал 3 раза", callback_data="tpl_gym3"))
    builder.row(InlineKeyboardButton(text="🏋️ Зал + 🏃 Бег", callback_data="tpl_gym_run"))
    builder.row(InlineKeyboardButton(text="🏠 Дома", callback_data="tpl_home3"))
    builder.row(InlineKeyboardButton(text="🧘 Йога + 🏃 Бег", callback_data="tpl_yoga_run"))
    builder.row(InlineKeyboardButton(text="⚙️ Настроить свою неделю", callback_data="tpl_custom"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="onboard_back_fitness"))
    return builder.as_markup()


DAY_NAMES = {1: "Понедельник", 2: "Вторник", 3: "Среда", 4: "Четверг", 5: "Пятница", 6: "Суббота", 7: "Воскресенье"}
DAY_EMOJIS = {"gym": "🏋️", "home": "🏠", "run": "🏃", "yoga": "🧘", "sport": "⚽", "rest": "😴"}


def week_day_activity_kb(day: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏋️ Зал", callback_data=f"wd_{day}_gym"),
        InlineKeyboardButton(text="🏠 Дома", callback_data=f"wd_{day}_home"),
        InlineKeyboardButton(text="🏃 Бег", callback_data=f"wd_{day}_run"),
    )
    builder.row(
        InlineKeyboardButton(text="🧘 Йога", callback_data=f"wd_{day}_yoga"),
        InlineKeyboardButton(text="⚽ Спорт", callback_data=f"wd_{day}_sport"),
        InlineKeyboardButton(text="😴 Отдых", callback_data=f"wd_{day}_rest"),
    )
    return builder.as_markup()


# ── Situation (nutrition help) ─────────────────────────

def situation_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎂 Застолье / день рождения", callback_data="situ_party"))
    builder.row(InlineKeyboardButton(text="🛒 Я в магазине", callback_data="situ_shop"))
    builder.row(InlineKeyboardButton(text="🍕 Хочу заказать еду", callback_data="situ_delivery"))
    builder.row(
        InlineKeyboardButton(text="🏃 До трени", callback_data="situ_preworkout"),
        InlineKeyboardButton(text="😴 Поздний ужин", callback_data="situ_late_meal"),
    )
    builder.row(InlineKeyboardButton(text="💬 Другое — напишу", callback_data="situ_custom"))
    builder.row(InlineKeyboardButton(text="◀️ Меню", callback_data="menu_back"))
    return builder.as_markup()


def shop_category_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🥩 Мясо/рыба", callback_data="shop_meat"),
        InlineKeyboardButton(text="🥛 Молочка", callback_data="shop_dairy"),
    )
    builder.row(
        InlineKeyboardButton(text="🍞 Крупы/хлеб", callback_data="shop_grain"),
        InlineKeyboardButton(text="🥦 Овощи", callback_data="shop_veg"),
    )
    builder.row(
        InlineKeyboardButton(text="🍫 Перекусы", callback_data="shop_snack"),
        InlineKeyboardButton(text="💬 Другое", callback_data="shop_custom"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="situ_menu"))
    return builder.as_markup()


def after_situation_kb(message_db_id: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if message_db_id:
        short_id = message_db_id.replace("-", "")
        builder.row(
            InlineKeyboardButton(text="👍 Полезно", callback_data=f"fb_up_{short_id}"),
            InlineKeyboardButton(text="👎 Не то", callback_data=f"fb_down_{short_id}"),
        )
    builder.row(
        InlineKeyboardButton(text="💬 Ещё вопрос", callback_data="situ_menu"),
        InlineKeyboardButton(text="◀️ Меню", callback_data="menu_back"),
    )
    return builder.as_markup()


# ── Exercise logging ───────────────────────────────────

def exercise_log_action_kb(ex_idx: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Так же", callback_data=f"log_same_{ex_idx}"),
        InlineKeyboardButton(text="📈 +2.5кг", callback_data=f"log_up_{ex_idx}"),
        InlineKeyboardButton(text="✏️ Другое", callback_data=f"log_edit_{ex_idx}"),
    )
    builder.row(InlineKeyboardButton(text="⏭ Пропустить запись", callback_data="log_skip"))
    return builder.as_markup()


def recent_exercises_kb(exercises: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    """exercises = [(exercise_name, exercise_label), ...]"""
    builder = InlineKeyboardBuilder()
    for name, label in exercises[:6]:
        builder.row(InlineKeyboardButton(text=label, callback_data=f"logex_{name[:20]}"))
    builder.row(InlineKeyboardButton(text="✏️ Другое — напишу название", callback_data="logex_custom"))
    builder.row(InlineKeyboardButton(text="◀️ Меню", callback_data="menu_back"))
    return builder.as_markup()
