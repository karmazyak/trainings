"""5-tap onboarding: goal → fitness_level → gender → training_style → activity_level."""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from tg_bot import prompts, texts
from tg_bot.api_client import AreteAPI
from tg_bot.db import save_user, set_conversation_id
from tg_bot.keyboards import (
    ACTIVITY_LABELS,
    FITNESS_LABELS,
    GOAL_LABELS,
    TRAINING_STYLE_LABELS,
    activity_level_kb,
    after_skill_kb,
    fitness_level_kb,
    gender_kb,
    main_menu_kb,
    training_style_kb,
)
from tg_bot.states import QuickOnboardingStates

logger = logging.getLogger(__name__)
router = Router()


# ── Step 1: Goal ─────────────────────────────────────────

@router.callback_query(QuickOnboardingStates.goal, F.data.startswith("goal_"))
async def process_goal(cb: CallbackQuery, state: FSMContext):
    value = cb.data.replace("goal_", "")
    await state.update_data(goal=GOAL_LABELS.get(value, value))
    await state.set_state(QuickOnboardingStates.fitness_level)
    await cb.message.edit_text(texts.ONBOARDING_FITNESS, reply_markup=fitness_level_kb())
    await cb.answer()


# ── Step 2: Fitness Level ────────────────────────────────

@router.callback_query(QuickOnboardingStates.fitness_level, F.data.startswith("fitness_"))
async def process_fitness(cb: CallbackQuery, state: FSMContext):
    value = cb.data.replace("fitness_", "")
    await state.update_data(fitness_level=FITNESS_LABELS.get(value, value))
    await state.set_state(QuickOnboardingStates.gender)
    await cb.message.edit_text(texts.ONBOARDING_GENDER, reply_markup=gender_kb())
    await cb.answer()


# ── Step 3: Gender → Training Style ──────────────────────

@router.callback_query(QuickOnboardingStates.gender, F.data.startswith("gender_"))
async def process_gender(cb: CallbackQuery, state: FSMContext):
    value = cb.data.replace("gender_", "")
    await state.update_data(gender=value)
    await state.set_state(QuickOnboardingStates.training_style)
    await cb.message.edit_text(texts.ONBOARDING_TRAINING_STYLE, reply_markup=training_style_kb())
    await cb.answer()


# ── Step 4: Training Style → Activity Level ─────────────

@router.callback_query(QuickOnboardingStates.training_style, F.data.startswith("style_"))
async def process_training_style(cb: CallbackQuery, state: FSMContext):
    style_value = cb.data.replace("style_", "")
    await state.update_data(training_style=style_value)
    await state.set_state(QuickOnboardingStates.activity_level)
    await cb.message.edit_text(texts.ONBOARDING_ACTIVITY_LEVEL, reply_markup=activity_level_kb())
    await cb.answer()


# ── Step 5: Activity Level → Create profile → First workout ─

@router.callback_query(QuickOnboardingStates.activity_level, F.data.startswith("activity_"))
async def process_activity_level(cb: CallbackQuery, state: FSMContext, api: AreteAPI):
    activity_value = cb.data.replace("activity_", "")
    data = await state.get_data()
    await state.clear()

    # Create profile with all collected data
    payload = {
        "name": data["name"],
        "goal": data.get("goal"),
        "fitness_level": data.get("fitness_level"),
        "gender": data.get("gender"),
        "training_style": data.get("training_style"),
        "activity_level": ACTIVITY_LABELS.get(activity_value, activity_value),
    }

    try:
        result = await api.create_user(payload)
        backend_user_id = result["id"]
        await save_user(cb.from_user.id, backend_user_id)
    except Exception:
        logger.exception("Failed to create user")
        await cb.message.edit_text(texts.PROFILE_ERROR)
        await cb.answer()
        return

    # Generate first workout — the "aha moment"
    await cb.message.edit_text(texts.GENERATING_FIRST_WORKOUT)

    try:
        chat_result = await api.chat(
            user_id=backend_user_id,
            message=prompts.WORKOUT_TODAY,
            agent="trainer",
        )
        new_conv_id = chat_result.get("conversation_id")
        if new_conv_id:
            await set_conversation_id(cb.from_user.id, new_conv_id)

        response = chat_result.get("message", "")
        if len(response) > 4000:
            response = response[:4000] + "..."

        await cb.message.answer(
            f"🏋️ <b>Твоя первая тренировка</b>\n\n{response}",
            reply_markup=after_skill_kb("skill_workout_today", "Новая тренировка"),
        )
    except Exception:
        logger.exception("Failed to generate first workout")
        await cb.message.answer("Профиль создан! Выбери действие в меню.")

    await cb.message.answer(texts.MAIN_MENU_TITLE, reply_markup=main_menu_kb())
    await cb.answer()
