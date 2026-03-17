"""Profile view & inline editing."""

import logging
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from tg_bot import texts
from tg_bot.api_client import AreteAPI
from tg_bot.keyboards import (
    ACTIVITY_LABELS,
    FITNESS_LABELS,
    GOAL_LABELS,
    TRAINING_STYLE_LABELS,
    activity_level_kb,
    edit_profile_kb,
    fitness_level_kb,
    goal_kb,
    profile_kb,
    training_style_kb,
)
from tg_bot.states import EditProfileStates

logger = logging.getLogger(__name__)
router = Router()

# Fields that use inline keyboards (callback-based)
KEYBOARD_FIELDS = {
    "edit_goal": ("goal", "🎯 Выбери новую цель:", goal_kb),
    "edit_fitness_level": ("fitness_level", "💪 Выбери уровень:", fitness_level_kb),
    "edit_training_style": ("training_style", "🏋️ Выбери стиль:", training_style_kb),
    "edit_activity_level": ("activity_level", "🏃 Как часто тренируешься?", activity_level_kb),
}

# Fields that need text input
TEXT_FIELDS = {"edit_height_cm", "edit_weight_kg", "edit_dietary_restrictions", "edit_allergies", "edit_limitations"}

# Callback prefix → (field_name, labels_dict)
CALLBACK_MAPS = {
    "editval_goal_": ("goal", GOAL_LABELS),
    "editval_fitness_": ("fitness_level", FITNESS_LABELS),
    "editval_style_": ("training_style", None),  # raw value
    "editval_activity_": ("activity_level", ACTIVITY_LABELS),
}


def _format_profile(data: dict) -> str:
    gender_map = {"male": "Мужской", "female": "Женский"}
    style_map = {"gym": "🏋️ Зал", "home": "🏠 Дома", "crossfit": "🤸 Кроссфит", "running": "🏃 Бег / Йога"}
    lines = [
        f"👤 <b>Имя:</b> {escape(str(data.get('name', '—')))}",
        f"⚧ <b>Пол:</b> {escape(gender_map.get(data.get('gender', ''), '—'))}",
        f"🎂 <b>Возраст:</b> {data.get('age') or '—'}",
        f"📏 <b>Рост:</b> {data.get('height_cm') or '—'} см",
        f"⚖️ <b>Вес:</b> {data.get('weight_kg') or '—'} кг",
        f"🎯 <b>Цель:</b> {escape(str(data.get('goal') or '—'))}",
        f"💪 <b>Уровень:</b> {escape(str(data.get('fitness_level') or '—'))}",
        f"🏋️ <b>Стиль:</b> {escape(style_map.get(data.get('training_style', ''), '—'))}",
        f"🏃 <b>Активность:</b> {escape(str(data.get('activity_level') or '—'))}",
        f"⚠️ <b>Ограничения:</b> {escape(str(data.get('limitations') or 'Нет'))}",
        f"🍽 <b>Питание:</b> {escape(str(data.get('dietary_restrictions') or 'Нет'))}",
        f"🤧 <b>Аллергии:</b> {escape(str(data.get('allergies') or 'Нет'))}",
    ]
    return "\n".join(lines)


async def _show_profile(target, api: AreteAPI, user_data: dict, edit: bool = True):
    """Show profile. target can be Message or CallbackQuery.message."""
    profile = await api.get_user(user_data["backend_user_id"])
    text = f"👤 <b>Мой профиль</b>\n\n{_format_profile(profile)}"
    kb = profile_kb()
    if hasattr(target, "edit_text"):
        try:
            await target.edit_text(text, reply_markup=kb)
        except Exception:
            await target.answer(text, reply_markup=kb)
    else:
        await target.answer(text, reply_markup=kb)


# ── View Profile ─────────────────────────────────────────


@router.message(Command("profile"))
async def cmd_profile(message: Message, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await message.answer(texts.NOT_REGISTERED)
        return
    try:
        await _show_profile(message, api, user_data)
    except Exception:
        logger.exception("Failed to get profile")
        await message.answer(texts.SERVER_ERROR)


@router.callback_query(lambda cb: cb.data == "menu_profile")
async def menu_profile(cb: CallbackQuery, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    try:
        await _show_profile(cb.message, api, user_data)
    except Exception:
        logger.exception("Failed to get profile")
        await cb.message.edit_text(texts.SERVER_ERROR)
    await cb.answer()


# ── Edit Profile: choose field ───────────────────────────


@router.callback_query(lambda cb: cb.data == "edit_profile")
async def edit_profile_start(cb: CallbackQuery, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await cb.message.edit_text(texts.EDIT_PROFILE_CHOOSE, reply_markup=edit_profile_kb())
    await cb.answer()


# ── Edit: keyboard-based fields (goal, fitness, style, activity) ──


@router.callback_query(lambda cb: cb.data in KEYBOARD_FIELDS)
async def edit_keyboard_field(cb: CallbackQuery, state: FSMContext, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return

    field_name, prompt_text, kb_func = KEYBOARD_FIELDS[cb.data]

    # Build keyboard with "editval_" prefix so we can distinguish from onboarding
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    original_kb = kb_func()
    builder = InlineKeyboardBuilder()

    # Remap callbacks: goal_weight_loss → editval_goal_weight_loss
    prefix_map = {
        "goal": "editval_goal_",
        "fitness_level": "editval_fitness_",
        "training_style": "editval_style_",
        "activity_level": "editval_activity_",
    }
    prefix = prefix_map[field_name]

    for row in original_kb.inline_keyboard:
        new_row = []
        for btn in row:
            # Strip original prefix, add editval prefix
            old_data = btn.callback_data or ""
            # Extract the value part after the first underscore group
            # e.g. "goal_weight_loss" → "weight_loss", "style_gym" → "gym"
            parts = old_data.split("_", 1)
            value = parts[1] if len(parts) > 1 else old_data
            new_row.append(InlineKeyboardButton(text=btn.text, callback_data=f"{prefix}{value}"))
        builder.row(*new_row)

    builder.row(InlineKeyboardButton(text="◀️ Отмена", callback_data="edit_profile"))

    await cb.message.edit_text(prompt_text, reply_markup=builder.as_markup())
    await cb.answer()


@router.callback_query(lambda cb: any(cb.data.startswith(p) for p in CALLBACK_MAPS))
async def save_keyboard_field(cb: CallbackQuery, api: AreteAPI, user_data: dict | None):
    """Save value selected via inline keyboard."""
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return

    # Determine which field
    for prefix, (field_name, labels) in CALLBACK_MAPS.items():
        if cb.data.startswith(prefix):
            raw_value = cb.data[len(prefix):]
            if labels:
                value = labels.get(raw_value, raw_value)
            else:
                value = raw_value
            break
    else:
        await cb.answer("Ошибка")
        return

    try:
        await api.update_user(user_data["backend_user_id"], {field_name: value})
    except Exception:
        logger.exception("Failed to update %s", field_name)
        await cb.message.edit_text(texts.SERVER_ERROR)
        await cb.answer()
        return

    await cb.answer("✅ Сохранено!")

    # Show updated profile
    try:
        await _show_profile(cb.message, api, user_data)
    except Exception:
        await cb.message.edit_text(texts.EDIT_PROFILE_SAVED)


# ── Edit: text-input fields (height, weight, allergies, etc.) ──


@router.callback_query(lambda cb: cb.data in TEXT_FIELDS)
async def edit_text_field(cb: CallbackQuery, state: FSMContext, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return

    field_name = cb.data.replace("edit_", "")  # e.g. "height_cm", "weight_kg"
    prompt = texts.EDIT_FIELD_PROMPTS.get(field_name, f"Введи новое значение для {field_name}:")

    await state.set_state(EditProfileStates.entering_value)
    await state.update_data(editing_field=field_name)
    await cb.message.edit_text(prompt)
    await cb.answer()


@router.message(EditProfileStates.entering_value, F.text)
async def save_text_field(message: Message, state: FSMContext, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await message.answer(texts.NOT_REGISTERED)
        await state.clear()
        return

    data = await state.get_data()
    field_name = data.get("editing_field", "")
    await state.clear()

    raw = message.text.strip()

    # Validate numeric fields
    if field_name == "height_cm":
        try:
            value = float(raw.replace(",", "."))
            if not 100 <= value <= 250:
                raise ValueError
        except ValueError:
            await message.answer("Рост должен быть числом от 100 до 250 см. Попробуй ещё:")
            return
        update = {"height_cm": value}

    elif field_name == "weight_kg":
        try:
            value = float(raw.replace(",", "."))
            if not 30 <= value <= 300:
                raise ValueError
        except ValueError:
            await message.answer("Вес должен быть числом от 30 до 300 кг. Попробуй ещё:")
            return
        update = {"weight_kg": value}

    else:
        # Text fields: dietary_restrictions, allergies, limitations
        value = None if raw.lower() in ("нет", "no", "-", "—") else raw
        update = {field_name: value}

    try:
        await api.update_user(user_data["backend_user_id"], update)
    except Exception:
        logger.exception("Failed to update %s", field_name)
        await message.answer(texts.SERVER_ERROR)
        return

    await message.answer(texts.EDIT_PROFILE_SAVED)

    # Show updated profile
    try:
        await _show_profile(message, api, user_data)
    except Exception:
        pass
