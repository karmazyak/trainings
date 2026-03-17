"""Catch-all handler for free-text chat messages (power users)."""

import logging
from html import escape

import httpx
from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import Message

from tg_bot import texts
from tg_bot.api_client import AreteAPI
from tg_bot.db import set_conversation_id
from tg_bot.keyboards import main_menu_kb
from tg_bot.states import (
    EditProfileStates,
    FeedbackStates,
    QuickOnboardingStates,
    SkillStates,
    VideoAnalysisStates,
)

logger = logging.getLogger(__name__)
router = Router()


@router.message(
    F.text,
    ~StateFilter(
        QuickOnboardingStates,
        SkillStates,
        FeedbackStates,
        VideoAnalysisStates,
        EditProfileStates,
    ),
)
async def handle_chat_message(
    message: Message, api: AreteAPI, user_data: dict | None
):
    if not user_data:
        await message.answer(texts.NOT_REGISTERED)
        return

    backend_user_id = user_data["backend_user_id"]
    conversation_id = user_data.get("conversation_id")
    agent_mode = user_data.get("agent_mode", "auto")

    status_msg = await message.answer(texts.THINKING)

    try:
        result = await api.chat(
            user_id=backend_user_id,
            message=message.text,
            agent=agent_mode,
            conversation_id=conversation_id,
        )
    except httpx.HTTPStatusError:
        logger.exception("Chat API error")
        await status_msg.edit_text(texts.SERVER_ERROR)
        return
    except Exception:
        logger.exception("Chat error")
        await status_msg.edit_text(texts.SERVER_ERROR)
        return

    new_conv_id = result.get("conversation_id")
    if new_conv_id and new_conv_id != conversation_id:
        await set_conversation_id(message.from_user.id, new_conv_id)

    agent_used = result.get("agent_used", "auto")
    agent_label = texts.AGENT_LABELS.get(agent_used, "🏛 Arete")
    response = result.get("message", "")

    response_text = f"<b>{escape(agent_label)}</b>\n\n{response}"

    sources = result.get("sources", [])
    if sources:
        source_lines = []
        for s in sources[:5]:
            book = s.get("book", "")
            chapter = s.get("chapter")
            line = f"  — <i>{escape(book)}"
            if chapter:
                line += f", {escape(chapter)}</i>"
            else:
                line += "</i>"
            source_lines.append(line)
        response_text += "\n\n📚 <b>Источники:</b>\n" + "\n".join(source_lines)

    if len(response_text) > 4000:
        response_text = response_text[:4000] + "..."

    try:
        await status_msg.edit_text(response_text)
    except Exception:
        plain = f"{agent_label}\n\n{result.get('message', '')}"
        if len(plain) > 4000:
            plain = plain[:4000] + "..."
        try:
            await status_msg.edit_text(plain, parse_mode=None)
        except Exception:
            logger.exception("Failed to send response")
