"""Situational nutrition help — party, shop, delivery, etc."""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from tg_bot import texts
from tg_bot.api_client import AreteAPI
from tg_bot.keyboards import (
    after_situation_kb, main_menu_kb, shop_category_kb, situation_kb,
)
from tg_bot.states import SituationStates
from tg_bot.utils import send_long_new

logger = logging.getLogger(__name__)
router = Router()


# ── Situation menu ──────────────────────────────────────


@router.callback_query(lambda cb: cb.data == "situ_menu")
async def show_situation_menu(cb: CallbackQuery, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await cb.answer()
    await cb.message.edit_text(texts.SITUATION_MENU, reply_markup=situation_kb())


# ── Direct situations ───────────────────────────────────


SITUATION_CALLBACKS = {
    "situ_party": "party",
    "situ_delivery": "delivery",
    "situ_preworkout": "preworkout",
    "situ_late_meal": "late_meal",
}


@router.callback_query(lambda cb: cb.data in SITUATION_CALLBACKS)
async def handle_situation(cb: CallbackQuery, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await cb.answer()

    situation = SITUATION_CALLBACKS[cb.data]
    status_msg = await cb.message.edit_text(texts.THINKING)

    try:
        result = await api.chat_situation(user_data["backend_user_id"], situation)
    except Exception:
        logger.exception("Situation chat failed")
        await status_msg.edit_text(texts.SERVER_ERROR, reply_markup=main_menu_kb())
        return

    response = result.get("message", "")
    message_db_id = result.get("message_db_id")
    text = f"🥗 <b>Нутрициолог</b>\n\n{response}"

    try:
        await status_msg.edit_text(text, reply_markup=after_situation_kb(message_db_id))
    except Exception:
        # Message too long — send new
        await status_msg.delete()
        await cb.message.answer(text, reply_markup=after_situation_kb(message_db_id))


# ── Shop flow ───────────────────────────────────────────


@router.callback_query(lambda cb: cb.data == "situ_shop")
async def show_shop_categories(cb: CallbackQuery, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await cb.answer()
    await cb.message.edit_text(texts.SHOP_MENU, reply_markup=shop_category_kb())


@router.callback_query(lambda cb: cb.data and cb.data.startswith("shop_") and cb.data != "shop_custom")
async def handle_shop_category(cb: CallbackQuery, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await cb.answer()

    subcategory = cb.data.replace("shop_", "")
    status_msg = await cb.message.edit_text(texts.THINKING)

    try:
        result = await api.chat_situation(user_data["backend_user_id"], "shop", subcategory=subcategory)
    except Exception:
        logger.exception("Shop situation failed")
        await status_msg.edit_text(texts.SERVER_ERROR, reply_markup=main_menu_kb())
        return

    response = result.get("message", "")
    message_db_id = result.get("message_db_id")
    text = f"🥗 <b>Нутрициолог</b>\n\n{response}"

    try:
        await status_msg.edit_text(text, reply_markup=after_situation_kb(message_db_id))
    except Exception:
        await status_msg.delete()
        await cb.message.answer(text, reply_markup=after_situation_kb(message_db_id))


# ── Custom situation ────────────────────────────────────


@router.callback_query(lambda cb: cb.data in ("situ_custom", "shop_custom"))
async def start_custom_situation(cb: CallbackQuery, state: FSMContext, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await cb.answer()
    await state.set_state(SituationStates.custom_situation)
    await cb.message.edit_text(texts.SITUATION_CUSTOM)


@router.message(SituationStates.custom_situation, F.text)
async def handle_custom_situation(message: Message, state: FSMContext, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await message.answer(texts.NOT_REGISTERED)
        return
    await state.clear()

    status_msg = await message.answer(texts.THINKING)

    try:
        result = await api.chat_situation(user_data["backend_user_id"], message.text)
    except Exception:
        logger.exception("Custom situation failed")
        await status_msg.edit_text(texts.SERVER_ERROR, reply_markup=main_menu_kb())
        return

    response = result.get("message", "")
    message_db_id = result.get("message_db_id")
    text = f"🥗 <b>Нутрициолог</b>\n\n{response}"

    try:
        await status_msg.edit_text(text, reply_markup=after_situation_kb(message_db_id))
    except Exception:
        await status_msg.delete()
        await message.answer(text, reply_markup=after_situation_kb(message_db_id))
