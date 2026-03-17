import logging
from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from tg_bot import texts
from tg_bot.api_client import AreteAPI
from tg_bot.keyboards import profile_kb

logger = logging.getLogger(__name__)
router = Router()


def _format_profile(data: dict) -> str:
    gender_map = {"male": "Мужской", "female": "Женский"}
    style_map = {"gym": "🏋️ Зал", "home": "🏠 Дома", "crossfit": "🤸 Кроссфит", "running": "🏃 Бег / Йога"}
    lines = [
        f"👤 <b>Имя:</b> {escape(str(data.get('name', '—')))}",
        f"⚧ <b>Пол:</b> {escape(gender_map.get(data.get('gender', ''), '—'))}",
        f"🎂 <b>Возраст:</b> {data.get('age', '—')}",
        f"📏 <b>Рост:</b> {data.get('height_cm', '—')} см",
        f"⚖️ <b>Вес:</b> {data.get('weight_kg', '—')} кг",
        f"🎯 <b>Цель:</b> {escape(str(data.get('goal', '—')))}",
        f"💪 <b>Уровень:</b> {escape(str(data.get('fitness_level', '—')))}",
        f"🏋️ <b>Стиль:</b> {escape(style_map.get(data.get('training_style', ''), '—'))}",
        f"🏃 <b>Активность:</b> {escape(str(data.get('activity_level', '—')))}",
        f"⚠️ <b>Ограничения:</b> {escape(str(data.get('limitations') or 'Нет'))}",
        f"🍽 <b>Питание:</b> {escape(str(data.get('dietary_restrictions') or 'Нет'))}",
        f"🤧 <b>Аллергии:</b> {escape(str(data.get('allergies') or 'Нет'))}",
    ]
    return "\n".join(lines)


@router.message(Command("profile"))
async def cmd_profile(message: Message, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await message.answer(texts.NOT_REGISTERED)
        return
    try:
        profile = await api.get_user(user_data["backend_user_id"])
        text = f"👤 <b>Мой профиль</b>\n\n{_format_profile(profile)}"
        await message.answer(text, reply_markup=profile_kb())
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
        profile = await api.get_user(user_data["backend_user_id"])
        text = f"👤 <b>Мой профиль</b>\n\n{_format_profile(profile)}"
        await cb.message.edit_text(text, reply_markup=profile_kb())
    except Exception:
        logger.exception("Failed to get profile")
        await cb.message.edit_text(texts.SERVER_ERROR)
    await cb.answer()
