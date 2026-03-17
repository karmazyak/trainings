from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ── Main menu (action-first) ────────────────────────────

def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Мой день", callback_data="skill_my_day"),
    )
    builder.row(
        InlineKeyboardButton(text="🏋️ Тренировка на сегодня", callback_data="skill_workout_today"),
        InlineKeyboardButton(text="🥗 Питание на сегодня", callback_data="skill_meal_today"),
    )
    builder.row(
        InlineKeyboardButton(text="📋 Программа на неделю", callback_data="skill_workout_week"),
        InlineKeyboardButton(text="🍽 Рацион на неделю", callback_data="skill_meal_week"),
    )
    builder.row(
        InlineKeyboardButton(text="⚡ Полный план (трени + еда)", callback_data="skill_full_plan"),
    )
    builder.row(
        InlineKeyboardButton(text="💬 Вопрос тренеру", callback_data="skill_ask_trainer"),
        InlineKeyboardButton(text="💬 Вопрос нутрициологу", callback_data="skill_ask_dietologist"),
    )
    builder.row(
        InlineKeyboardButton(text="📹 Проверка техники", callback_data="menu_video"),
    )
    builder.row(
        InlineKeyboardButton(text="👤 Профиль", callback_data="menu_profile"),
        InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu_settings"),
    )
    return builder.as_markup()


# ── After-skill keyboard ────────────────────────────────

def after_skill_kb(
    repeat_callback: str, repeat_label: str, message_db_id: str | None = None
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if message_db_id:
        # Truncate UUID to fit callback_data limit (64 bytes)
        short_id = message_db_id.replace("-", "")[:24]
        builder.row(
            InlineKeyboardButton(text="👍", callback_data=f"fb_up_{short_id}"),
            InlineKeyboardButton(text="👎", callback_data=f"fb_down_{short_id}"),
        )
    builder.row(
        InlineKeyboardButton(text=f"🔄 {repeat_label}", callback_data=repeat_callback),
        InlineKeyboardButton(text="◀️ Меню", callback_data="menu_back"),
    )
    return builder.as_markup()


def after_ask_kb(repeat_callback: str, message_db_id: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if message_db_id:
        short_id = message_db_id.replace("-", "")[:24]
        builder.row(
            InlineKeyboardButton(text="👍", callback_data=f"fb_up_{short_id}"),
            InlineKeyboardButton(text="👎", callback_data=f"fb_down_{short_id}"),
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
        InlineKeyboardButton(text="🔥 Продвинутый", callback_data="fitness_advanced"),
    )
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
    return builder.as_markup()


TRAINING_STYLE_LABELS = {
    "gym": "Зал",
    "home": "Дома",
    "crossfit": "Кроссфит",
    "running": "Бег / Йога",
}


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
    return builder.as_markup()


EXERCISE_LABELS = {
    "squats": "Приседания",
    "bench_press": "Жим лёжа",
    "deadlift": "Становая тяга",
    "pullups": "Подтягивания",
}


# ── Profile ──────────────────────────────────────────────

def profile_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="◀️ Назад", callback_data="menu_back"),
    )
    return builder.as_markup()
