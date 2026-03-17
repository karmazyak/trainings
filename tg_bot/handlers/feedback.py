"""Feedback handlers: thumbs up/down on agent responses."""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from tg_bot import texts
from tg_bot.api_client import AreteAPI
from tg_bot.keyboards import main_menu_kb
from tg_bot.states import FeedbackStates

logger = logging.getLogger(__name__)
router = Router()


def _expand_short_id(short_id: str) -> str:
    """Expand truncated hex back to UUID format (best-effort)."""
    # Pad to 32 hex chars if needed
    padded = short_id.ljust(32, "0")
    return f"{padded[:8]}-{padded[8:12]}-{padded[12:16]}-{padded[16:20]}-{padded[20:32]}"


@router.callback_query(lambda cb: cb.data and cb.data.startswith("fb_up_"))
async def feedback_up(cb: CallbackQuery, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await cb.answer()
        return

    short_id = cb.data[6:]  # after "fb_up_"
    message_db_id = _expand_short_id(short_id)

    try:
        await api.submit_feedback(
            user_id=user_data["backend_user_id"],
            message_id=message_db_id,
            rating=5,
        )
    except Exception:
        logger.exception("Failed to submit positive feedback")

    await cb.answer(texts.FEEDBACK_THANKS_UP, show_alert=False)


@router.callback_query(lambda cb: cb.data and cb.data.startswith("fb_down_"))
async def feedback_down(cb: CallbackQuery, state: FSMContext, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await cb.answer()
        return

    short_id = cb.data[8:]  # after "fb_down_"
    message_db_id = _expand_short_id(short_id)

    # Submit negative feedback immediately (comment will be added later if provided)
    try:
        await api.submit_feedback(
            user_id=user_data["backend_user_id"],
            message_id=message_db_id,
            rating=1,
        )
    except Exception:
        logger.exception("Failed to submit negative feedback")

    # Ask for optional comment
    await state.update_data(feedback_message_id=message_db_id)
    await state.set_state(FeedbackStates.collecting_comment)
    await cb.answer()
    await cb.message.answer(texts.FEEDBACK_THANKS_DOWN)


@router.message(FeedbackStates.collecting_comment, F.text)
async def feedback_comment(message: Message, state: FSMContext, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await state.clear()
        return

    # Handle /skip
    if message.text.strip().lower() in ("/skip", "skip", "пропустить"):
        await state.clear()
        await message.answer(texts.FEEDBACK_SKIPPED)
        return

    data = await state.get_data()
    message_db_id = data.get("feedback_message_id")
    await state.clear()

    if message_db_id:
        try:
            await api.submit_feedback(
                user_id=user_data["backend_user_id"],
                message_id=message_db_id,
                rating=1,
                comment=message.text,
            )
        except Exception:
            logger.exception("Failed to submit feedback comment")

    await message.answer(texts.FEEDBACK_COMMENT_THANKS)
