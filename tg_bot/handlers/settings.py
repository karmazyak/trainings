import logging
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from tg_bot import texts
from tg_bot.db import reset_conversation, set_agent_mode
from tg_bot.keyboards import settings_kb

logger = logging.getLogger(__name__)
router = Router()

MODE_LABELS = {
    "auto": "🏛 Авто",
    "trainer": "🏋️ Тренер",
    "dietologist": "🥗 Нутрициолог",
}


@router.message(Command("settings"))
async def cmd_settings(message: Message, user_data: dict | None):
    if not user_data:
        await message.answer(texts.NOT_REGISTERED)
        return
    current = user_data.get("agent_mode", "auto")
    label = MODE_LABELS.get(current, "🏛 Авто")
    text = texts.SETTINGS_TEXT.format(mode=escape(label))
    await message.answer(text, reply_markup=settings_kb(current))


@router.callback_query(lambda cb: cb.data == "menu_settings")
async def menu_settings(cb: CallbackQuery, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    current = user_data.get("agent_mode", "auto")
    label = MODE_LABELS.get(current, "🏛 Авто")
    text = texts.SETTINGS_TEXT.format(mode=escape(label))
    await cb.message.edit_text(text, reply_markup=settings_kb(current))
    await cb.answer()


@router.message(Command("reset"))
async def cmd_reset(message: Message, user_data: dict | None):
    if not user_data:
        await message.answer(texts.NOT_REGISTERED)
        return
    await reset_conversation(message.from_user.id)
    await message.answer(texts.CONVERSATION_RESET)


@router.callback_query(F.data == "reset_conversation")
async def reset_conv_cb(cb: CallbackQuery, user_data: dict | None):
    if not user_data:
        await cb.answer("Сначала зарегистрируйся")
        return
    await reset_conversation(cb.from_user.id)
    await cb.answer("Диалог сброшен!")
    current = user_data.get("agent_mode", "auto")
    label = MODE_LABELS.get(current, "🏛 Авто")
    text = texts.SETTINGS_TEXT.format(mode=escape(label))
    await cb.message.edit_text(text, reply_markup=settings_kb(current))


@router.callback_query(F.data.startswith("mode_"))
async def change_mode(cb: CallbackQuery, user_data: dict | None):
    if not user_data:
        await cb.answer("Сначала зарегистрируйся")
        return

    mode = cb.data.replace("mode_", "")
    await set_agent_mode(cb.from_user.id, mode)
    user_data["agent_mode"] = mode

    label = MODE_LABELS.get(mode, "🏛 Авто")
    await cb.answer(f"Режим: {label}")

    text = texts.SETTINGS_TEXT.format(mode=escape(label))
    await cb.message.edit_text(text, reply_markup=settings_kb(mode))
