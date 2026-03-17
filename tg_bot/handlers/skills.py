"""Skill handlers: structured actions with plan caching."""

import logging
from html import escape

import httpx
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from tg_bot import prompts, texts
from tg_bot.api_client import AreteAPI
from tg_bot.db import set_conversation_id
from tg_bot.keyboards import after_ask_kb, after_skill_kb, main_menu_kb
from tg_bot.states import SkillStates

logger = logging.getLogger(__name__)
router = Router()

# Map callback → (plan_type, prompt, agent, repeat_callback, repeat_label)
PLAN_SKILLS = {
    "skill_workout_today": ("workout_today", prompts.WORKOUT_TODAY, "trainer", "skill_workout_today_new", "🔄 Новая тренировка"),
    "skill_workout_week": ("workout_week", prompts.WORKOUT_WEEK, "trainer", "skill_workout_week_new", "🔄 Новая программа"),
    "skill_meal_today": ("meal_today", prompts.MEAL_TODAY, "dietologist", "skill_meal_today_new", "🔄 Новый рацион"),
    "skill_meal_week": ("meal_week", prompts.MEAL_WEEK, "dietologist", "skill_meal_week_new", "🔄 Новый рацион"),
    "skill_full_plan": ("full_plan", prompts.FULL_PLAN, "auto", "skill_full_plan_new", "🔄 Новый план"),
}

# Force-regenerate callbacks (same skills but with force=True)
FORCE_REGEN = {
    "skill_workout_today_new": "skill_workout_today",
    "skill_workout_week_new": "skill_workout_week",
    "skill_meal_today_new": "skill_meal_today",
    "skill_meal_week_new": "skill_meal_week",
    "skill_full_plan_new": "skill_full_plan",
}

# Skills requiring height/weight check
NEEDS_PROFILE = {"skill_meal_today", "skill_meal_week", "skill_full_plan"}


# ── Helpers ──────────────────────────────────────────────


async def _send_long(bot_msg, text: str, reply_markup=None, parse_mode="HTML"):
    """Send potentially long text, splitting at Telegram's 4096 limit."""
    chunks = []
    while len(text) > 4000:
        split_at = text.rfind("\n", 0, 4000)
        if split_at == -1:
            split_at = 4000
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip()
    chunks.append(text)

    # First chunk — edit the "thinking" message
    try:
        await bot_msg.edit_text(chunks[0], parse_mode=parse_mode)
    except Exception:
        await bot_msg.edit_text(chunks[0], parse_mode=None)

    # Remaining chunks — new messages
    for i, chunk in enumerate(chunks[1:], 1):
        kb = reply_markup if i == len(chunks) - 1 else None
        try:
            await bot_msg.answer(chunk, reply_markup=kb, parse_mode=parse_mode)
        except Exception:
            await bot_msg.answer(chunk, reply_markup=kb, parse_mode=None)

    # If only one chunk, send menu as separate message
    if len(chunks) == 1 and reply_markup:
        await bot_msg.answer("⬇️", reply_markup=reply_markup)


async def _run_cached_skill(
    cb: CallbackQuery,
    api: AreteAPI,
    user_data: dict,
    skill_key: str,
    force: bool = False,
):
    """Run a skill with plan caching. Shows cached plan instantly, or generates new."""
    plan_type, prompt, agent, repeat_cb, repeat_label = PLAN_SKILLS[skill_key]
    backend_user_id = user_data["backend_user_id"]

    thinking = texts.THINKING_FULL if skill_key == "skill_full_plan" else texts.THINKING
    status_msg = await cb.message.edit_text(thinking)

    try:
        result = await api.get_plan(
            user_id=backend_user_id,
            plan_type=plan_type,
            prompt=prompt,
            force=force,
        )
    except httpx.HTTPStatusError:
        logger.exception("Plan API error")
        await status_msg.edit_text(texts.SERVER_ERROR)
        return
    except Exception:
        logger.exception("Plan error")
        await status_msg.edit_text(texts.SERVER_ERROR)
        return

    content = result.get("content", "")
    cached = result.get("cached", False)

    # Show cache status label
    cache_label = texts.PLAN_FROM_CACHE if cached else texts.PLAN_FRESH
    agent_label = texts.AGENT_LABELS.get(agent if agent != "auto" else "both", "🏛 Arete")

    text = f"<b>{escape(agent_label)}</b>  <i>{cache_label}</i>\n\n{content}"
    kb = after_skill_kb(repeat_cb, repeat_label)

    await _send_long(status_msg, text, reply_markup=kb)


async def _run_ask_skill(
    message: Message,
    api: AreteAPI,
    user_data: dict,
    agent: str,
    repeat_callback: str,
):
    """Handle free-text question to a specific agent (no caching)."""
    backend_user_id = user_data["backend_user_id"]
    conversation_id = user_data.get("conversation_id")

    status_msg = await message.answer(texts.THINKING)

    try:
        result = await api.chat(
            user_id=backend_user_id,
            message=message.text,
            agent=agent,
            conversation_id=conversation_id,
        )
    except Exception:
        logger.exception("Ask skill error")
        await status_msg.edit_text(texts.SERVER_ERROR)
        return

    new_conv_id = result.get("conversation_id")
    if new_conv_id and new_conv_id != conversation_id:
        await set_conversation_id(message.from_user.id, new_conv_id)

    agent_used = result.get("agent_used", agent)
    label = texts.AGENT_LABELS.get(agent_used, "🏛 Arete")
    response = result.get("message", "")

    text = f"<b>{escape(label)}</b>\n\n{response}"
    message_db_id = result.get("message_db_id")
    kb = after_ask_kb(repeat_callback, message_db_id=message_db_id)

    await _send_long(status_msg, text, reply_markup=kb)


# ── "My Day" — compact today view ────────────────────────


@router.callback_query(lambda cb: cb.data == "skill_my_day")
async def skill_my_day(cb: CallbackQuery, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await cb.answer()

    status_msg = await cb.message.edit_text(texts.MY_DAY_THINKING)

    try:
        result = await api.get_my_day(user_data["backend_user_id"])
    except Exception:
        logger.exception("My day error")
        await status_msg.edit_text(texts.SERVER_ERROR)
        return

    workout = result.get("workout")
    meal = result.get("meal")
    day_label = result.get("day_label", "")

    if not workout and not meal:
        await status_msg.edit_text(texts.MY_DAY_NO_PLANS, reply_markup=main_menu_kb())
        return

    parts = [texts.MY_DAY_HEADER.format(day_label=day_label)]

    if workout:
        parts.append("<b>🏋️ Тренировка</b>\n" + workout)

    if meal:
        parts.append("<b>🥗 Питание</b>\n" + meal)

    text = "\n\n".join(parts)
    kb = main_menu_kb()

    await _send_long(status_msg, text, reply_markup=kb)


# ── Cached Plan Skills ────────────────────────────────────


async def _check_profile_for_meal(
    cb: CallbackQuery,
    state: FSMContext,
    api: AreteAPI,
    user_data: dict,
    pending_skill: str,
) -> bool:
    """Check if height/weight are set. If not, start collection."""
    try:
        profile = await api.get_user(user_data["backend_user_id"])
    except Exception:
        logger.exception("Failed to get profile")
        await cb.message.edit_text(texts.SERVER_ERROR)
        return False

    if not profile.get("height_cm") or not profile.get("weight_kg"):
        await state.update_data(pending_skill=pending_skill)
        await state.set_state(SkillStates.collecting_height)
        await cb.message.edit_text(texts.NEED_HEIGHT)
        return False

    return True


@router.callback_query(lambda cb: cb.data in PLAN_SKILLS)
async def handle_plan_skill(cb: CallbackQuery, state: FSMContext, api: AreteAPI, user_data: dict | None):
    """Universal handler for all plan skills (with caching)."""
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await cb.answer()

    skill_key = cb.data

    # Check profile for meal skills
    if skill_key in NEEDS_PROFILE:
        ready = await _check_profile_for_meal(cb, state, api, user_data, skill_key)
        if not ready:
            return

    await _run_cached_skill(cb, api, user_data, skill_key, force=False)


@router.callback_query(lambda cb: cb.data in FORCE_REGEN)
async def handle_force_regen(cb: CallbackQuery, state: FSMContext, api: AreteAPI, user_data: dict | None):
    """Force-regenerate a plan (user clicked '🔄 Новая ...')."""
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await cb.answer()

    original_skill = FORCE_REGEN[cb.data]

    if original_skill in NEEDS_PROFILE:
        ready = await _check_profile_for_meal(cb, state, api, user_data, original_skill)
        if not ready:
            return

    await _run_cached_skill(cb, api, user_data, original_skill, force=True)


# ── Progressive Profiling: height/weight collection ─────


@router.message(SkillStates.collecting_height, F.text)
async def collect_height(message: Message, state: FSMContext):
    try:
        height = float(message.text.strip().replace(",", "."))
        if not 100 <= height <= 250:
            raise ValueError
    except ValueError:
        await message.answer("Введи рост числом (100-250 см):")
        return
    await state.update_data(height_cm=height)
    await state.set_state(SkillStates.collecting_weight)
    await message.answer(texts.NEED_WEIGHT)


@router.message(SkillStates.collecting_weight, F.text)
async def collect_weight(message: Message, state: FSMContext, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await message.answer(texts.NOT_REGISTERED)
        return

    try:
        weight = float(message.text.strip().replace(",", "."))
        if not 30 <= weight <= 300:
            raise ValueError
    except ValueError:
        await message.answer("Введи вес числом (30-300 кг):")
        return

    data = await state.get_data()
    pending_skill = data.get("pending_skill", "skill_meal_today")
    height_cm = data.get("height_cm")
    await state.clear()

    # Update backend profile with height/weight
    try:
        await api.update_user(
            user_data["backend_user_id"],
            {"height_cm": height_cm, "weight_kg": weight},
        )
    except Exception:
        logger.exception("Failed to update profile")

    await message.answer(texts.PROFILE_UPDATED_GENERATING)

    # Now generate via cached plan API
    if pending_skill in PLAN_SKILLS:
        plan_type, prompt_text, agent, repeat_cb, repeat_label = PLAN_SKILLS[pending_skill]

        # Add height/weight to prompt
        extra = f"\n\nМои данные: рост {height_cm} см, вес {weight} кг."
        full_prompt = prompt_text + extra

        backend_user_id = user_data["backend_user_id"]

        try:
            result = await api.get_plan(
                user_id=backend_user_id,
                plan_type=plan_type,
                prompt=full_prompt,
                force=True,
            )
        except Exception:
            logger.exception("Skill after profiling error")
            await message.answer(texts.SERVER_ERROR)
            return

        content = result.get("content", "")
        agent_label = texts.AGENT_LABELS.get(agent if agent != "auto" else "both", "🏛 Arete")
        text = f"<b>{escape(agent_label)}</b>  <i>{texts.PLAN_FRESH}</i>\n\n{content}"
        kb = after_skill_kb(repeat_cb, repeat_label)

        # Send (may need splitting)
        if len(text) > 4000:
            parts = []
            remaining = text
            while len(remaining) > 4000:
                split_at = remaining.rfind("\n", 0, 4000)
                if split_at == -1:
                    split_at = 4000
                parts.append(remaining[:split_at])
                remaining = remaining[split_at:].lstrip()
            parts.append(remaining)
            for i, part in enumerate(parts):
                part_kb = kb if i == len(parts) - 1 else None
                await message.answer(part, reply_markup=part_kb)
        else:
            await message.answer(text, reply_markup=kb)
    else:
        await message.answer("Готово! Используй меню для генерации планов.", reply_markup=main_menu_kb())


# ── Ask Trainer / Dietologist ────────────────────────────


@router.callback_query(lambda cb: cb.data == "skill_ask_trainer")
async def ask_trainer_start(cb: CallbackQuery, state: FSMContext, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await state.set_state(SkillStates.asking_trainer)
    await cb.message.edit_text(texts.ASK_TRAINER_PROMPT)
    await cb.answer()


@router.callback_query(lambda cb: cb.data == "skill_ask_dietologist")
async def ask_dietologist_start(cb: CallbackQuery, state: FSMContext, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await state.set_state(SkillStates.asking_dietologist)
    await cb.message.edit_text(texts.ASK_DIETOLOGIST_PROMPT)
    await cb.answer()


@router.message(SkillStates.asking_trainer, F.text)
async def ask_trainer_message(message: Message, state: FSMContext, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await message.answer(texts.NOT_REGISTERED)
        return
    await state.clear()
    await _run_ask_skill(message, api, user_data, agent="trainer", repeat_callback="skill_ask_trainer")


@router.message(SkillStates.asking_dietologist, F.text)
async def ask_dietologist_message(message: Message, state: FSMContext, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await message.answer(texts.NOT_REGISTERED)
        return
    await state.clear()
    await _run_ask_skill(message, api, user_data, agent="dietologist", repeat_callback="skill_ask_dietologist")
