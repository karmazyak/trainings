import logging
from html import escape
from io import BytesIO

import httpx
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from tg_bot import texts
from tg_bot.api_client import AreteAPI
from tg_bot.keyboards import EXERCISE_LABELS, exercise_name_kb
from tg_bot.states import VideoAnalysisStates

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.video | F.video_note)
async def handle_video(message: Message, state: FSMContext, user_data: dict | None):
    if not user_data:
        await message.answer(texts.NOT_REGISTERED)
        return

    file_id = (
        message.video.file_id if message.video else message.video_note.file_id
    )
    await state.update_data(video_file_id=file_id)
    await state.set_state(VideoAnalysisStates.waiting_exercise_name)
    await message.answer(texts.VIDEO_ASK_EXERCISE, reply_markup=exercise_name_kb())


@router.callback_query(
    VideoAnalysisStates.waiting_exercise_name, F.data.startswith("exercise_")
)
async def exercise_from_button(
    cb: CallbackQuery, state: FSMContext, api: AreteAPI, user_data: dict
):
    value = cb.data.replace("exercise_", "")
    exercise_name = EXERCISE_LABELS.get(value, value)
    await cb.answer()
    await _analyze(cb.message, state, api, user_data, exercise_name)


@router.message(VideoAnalysisStates.waiting_exercise_name, F.text)
async def exercise_from_text(
    message: Message, state: FSMContext, api: AreteAPI, user_data: dict
):
    await _analyze(message, state, api, user_data, message.text.strip())


async def _analyze(
    message: Message,
    state: FSMContext,
    api: AreteAPI,
    user_data: dict,
    exercise_name: str,
):
    data = await state.get_data()
    await state.clear()

    status_msg = await message.answer(texts.VIDEO_ANALYZING)

    try:
        file = await message.bot.get_file(data["video_file_id"])
        buffer = BytesIO()
        await message.bot.download_file(file.file_path, buffer)

        result = await api.analyze_exercise(
            user_id=user_data["backend_user_id"],
            exercise_name=exercise_name,
            video_bytes=buffer.getvalue(),
        )
    except httpx.HTTPStatusError:
        logger.exception("Exercise analysis API error")
        await status_msg.edit_text(texts.VIDEO_ERROR)
        return
    except Exception:
        logger.exception("Exercise analysis error")
        await status_msg.edit_text(texts.VIDEO_ERROR)
        return

    text = (
        f"<b>🏋️ Анализ: {escape(result['exercise_name'])}</b>\n\n"
        f"Повторений: {result['reps_count']}\n\n"
        f"📋 <b>Отчёт:</b>\n{escape(result['analysis_report'])}\n\n"
        f"💬 <b>Рекомендации тренера:</b>\n{escape(result['trainer_feedback'])}"
    )

    if len(text) > 4000:
        text = text[:4000] + "..."

    try:
        await status_msg.edit_text(text)
    except Exception:
        plain = (
            f"🏋️ Анализ: {result['exercise_name']}\n\n"
            f"Повторений: {result['reps_count']}\n\n"
            f"📋 Отчёт:\n{result['analysis_report']}\n\n"
            f"💬 Рекомендации тренера:\n{result['trainer_feedback']}"
        )
        await status_msg.edit_text(plain[:4000], parse_mode=None)
