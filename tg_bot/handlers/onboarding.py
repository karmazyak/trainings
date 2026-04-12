"""v2 onboarding: try question → goal → fitness → week template → create profile."""

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from tg_bot import texts
from tg_bot.api_client import AreteAPI
from tg_bot.db import save_user
from tg_bot.keyboards import (
    DAY_EMOJIS,
    DAY_NAMES,
    FITNESS_LABELS,
    GOAL_LABELS,
    after_try_kb,
    fitness_level_kb,
    goal_kb,
    main_menu_kb,
    try_question_kb,
    week_day_activity_kb,
    week_template_kb,
)
from tg_bot.states import OnboardingStates

logger = logging.getLogger(__name__)
router = Router()


# ── Try Question (aha moment) ───────────────────────────


TRY_QUESTIONS = {
    "try_q_chest": "Как накачать грудь?",
    "try_q_meal": "Что есть до тренировки?",
    "try_q_run": "С чего начать бегать?",
}


@router.callback_query(lambda cb: cb.data in TRY_QUESTIONS)
async def handle_try_question_button(cb: CallbackQuery, state: FSMContext, api: AreteAPI):
    await cb.answer()
    question = TRY_QUESTIONS[cb.data]
    status_msg = await cb.message.edit_text("⏳ Отвечаю...")

    try:
        result = await api.chat_try(question)
        response = result.get("message", "Не удалось получить ответ")
    except Exception:
        logger.exception("Try question failed")
        response = "❌ Не удалось получить ответ. Попробуй ещё раз."

    text = f"🏋️ <b>Тренер</b>\n\n{response}{texts.ONBOARDING_AFTER_TRY}"
    await status_msg.edit_text(text, reply_markup=after_try_kb())


@router.callback_query(lambda cb: cb.data == "try_q_custom")
async def handle_try_custom_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(OnboardingStates.try_question)
    await cb.message.edit_text(texts.ONBOARDING_TRY_QUESTION)


@router.message(OnboardingStates.try_question, F.text)
async def handle_try_custom_text(message: Message, state: FSMContext, api: AreteAPI):
    await state.clear()
    status_msg = await message.answer("⏳ Отвечаю...")

    try:
        result = await api.chat_try(message.text)
        response = result.get("message", "Не удалось получить ответ")
    except Exception:
        logger.exception("Try question failed")
        response = "❌ Не удалось получить ответ. Попробуй ещё раз."

    text = f"🏋️ <b>Тренер</b>\n\n{response}{texts.ONBOARDING_AFTER_TRY}"
    await status_msg.edit_text(text, reply_markup=after_try_kb())


# ── Start onboarding (after try question) ────────────────


@router.callback_query(lambda cb: cb.data == "onboard_start")
async def start_onboarding(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(OnboardingStates.goal)
    await cb.message.edit_text(texts.ONBOARDING_GOAL, reply_markup=goal_kb())


# ── Back navigation ──────────────────────────────────────


@router.callback_query(lambda cb: cb.data == "onboard_back_goal")
async def back_to_goal(cb: CallbackQuery, state: FSMContext):
    await state.set_state(OnboardingStates.goal)
    await cb.message.edit_text(texts.ONBOARDING_GOAL, reply_markup=goal_kb())
    await cb.answer()


@router.callback_query(lambda cb: cb.data == "onboard_back_fitness")
async def back_to_fitness(cb: CallbackQuery, state: FSMContext):
    await state.set_state(OnboardingStates.fitness_level)
    await cb.message.edit_text(texts.ONBOARDING_FITNESS, reply_markup=fitness_level_kb())
    await cb.answer()


# ── Step 1/2: Goal ──────────────────────────────────────


@router.callback_query(OnboardingStates.goal, F.data.startswith("goal_"))
async def process_goal(cb: CallbackQuery, state: FSMContext):
    value = cb.data.replace("goal_", "")
    await state.update_data(goal=GOAL_LABELS.get(value, value))
    await state.set_state(OnboardingStates.fitness_level)
    await cb.message.edit_text(texts.ONBOARDING_FITNESS, reply_markup=fitness_level_kb())
    await cb.answer()


# ── Step 1/2: Fitness Level ─────────────────────────────


@router.callback_query(OnboardingStates.fitness_level, F.data.startswith("fitness_"))
async def process_fitness(cb: CallbackQuery, state: FSMContext):
    value = cb.data.replace("fitness_", "")
    await state.update_data(fitness_level=FITNESS_LABELS.get(value, value))
    await state.set_state(OnboardingStates.week_template)
    await cb.message.edit_text(texts.ONBOARDING_WEEK, reply_markup=week_template_kb())
    await cb.answer()


# ── Step 2/2: Week Template ─────────────────────────────


@router.callback_query(OnboardingStates.week_template, F.data.startswith("tpl_"))
async def process_week_template(cb: CallbackQuery, state: FSMContext, api: AreteAPI):
    template = cb.data.replace("tpl_", "")

    if template == "custom":
        # Start custom day-by-day configuration
        await state.update_data(custom_days={}, current_day=1)
        await state.set_state(OnboardingStates.custom_week_day)
        progress = "Пн ❓ | Вт ❓ | Ср ❓ | Чт ❓ | Пт ❓ | Сб ❓ | Вс ❓"
        text = texts.ONBOARDING_CUSTOM_DAY.format(day_name=DAY_NAMES[1], progress=progress)
        await cb.message.edit_text(text, reply_markup=week_day_activity_kb(1))
        await cb.answer()
        return

    # Template selected — create user
    await cb.answer()
    data = await state.get_data()
    await _create_user_and_finish(cb, state, api, data, schedule_template=template)


# ── Custom Week Day Selection ────────────────────────────


@router.callback_query(OnboardingStates.custom_week_day, F.data.startswith("wd_"))
async def process_custom_day(cb: CallbackQuery, state: FSMContext, api: AreteAPI):
    # Parse: wd_{day}_{type}
    parts = cb.data.split("_")
    day = int(parts[1])
    activity = parts[2]

    data = await state.get_data()
    custom_days = data.get("custom_days", {})
    custom_days[str(day)] = activity

    if day < 7:
        # Move to next day
        next_day = day + 1
        await state.update_data(custom_days=custom_days, current_day=next_day)

        # Build progress string
        progress_parts = []
        short_days = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"}
        for d in range(1, 8):
            if str(d) in custom_days:
                emoji = DAY_EMOJIS.get(custom_days[str(d)], "❓")
                progress_parts.append(f"{short_days[d]} {emoji}")
            else:
                progress_parts.append(f"{short_days[d]} ❓")
        progress = " | ".join(progress_parts)

        text = texts.ONBOARDING_CUSTOM_DAY.format(day_name=DAY_NAMES[next_day], progress=progress)
        await cb.message.edit_text(text, reply_markup=week_day_activity_kb(next_day))
        await cb.answer()
    else:
        # All 7 days configured — create user
        await cb.answer()
        custom_days[str(day)] = activity
        await state.update_data(custom_days=custom_days)
        data = await state.get_data()

        # Build week_schedule list
        week_schedule = [
            {"day_of_week": int(d), "activity_type": t}
            for d, t in sorted(custom_days.items())
        ]
        await _create_user_and_finish(cb, state, api, data, week_schedule=week_schedule)


# ── Helper: Create user and show result ──────────────────


TEMPLATES = {
    "gym3": {1: "gym", 2: "rest", 3: "gym", 4: "rest", 5: "gym", 6: "rest", 7: "rest"},
    "gym_run": {1: "gym", 2: "run", 3: "rest", 4: "gym", 5: "rest", 6: "rest", 7: "rest"},
    "home3": {1: "home", 2: "rest", 3: "home", 4: "rest", 5: "home", 6: "rest", 7: "rest"},
    "yoga_run": {1: "yoga", 2: "run", 3: "yoga", 4: "run", 5: "yoga", 6: "rest", 7: "rest"},
}


async def _create_user_and_finish(
    cb: CallbackQuery,
    state: FSMContext,
    api: AreteAPI,
    data: dict,
    schedule_template: str | None = None,
    week_schedule: list | None = None,
):
    payload = {
        "name": data.get("name", cb.from_user.first_name),
        "goal": data.get("goal"),
        "fitness_level": data.get("fitness_level"),
    }

    if schedule_template:
        payload["schedule_template"] = schedule_template
    elif week_schedule:
        payload["week_schedule"] = week_schedule

    try:
        result = await api.create_user(payload)
        backend_user_id = result["id"]

        # Determine dominant training style for local storage
        training_style = result.get("training_style", "gym")
        preferred_days = result.get("preferred_training_days", "1,3,5")

        await save_user(
            cb.from_user.id,
            backend_user_id,
            training_style=training_style,
            preferred_training_days=preferred_days,
        )
    except Exception as exc:
        logger.exception("Failed to create user")
        await state.clear()
        await cb.message.edit_text(f"{texts.PROFILE_ERROR}\n\n<code>{str(exc)[:200]}</code>")
        return

    await state.clear()

    # Show success with schedule visualization
    short_days = {1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс"}
    schedule_text = ""

    if schedule_template:
        tpl = TEMPLATES.get(schedule_template, {})
        schedule_text = " | ".join(
            f"{short_days[d]} {DAY_EMOJIS.get(t, '❓')}" for d, t in sorted(tpl.items())
        )
    elif week_schedule:
        schedule_text = " | ".join(
            f"{short_days[s['day_of_week']]} {DAY_EMOJIS.get(s['activity_type'], '❓')}"
            for s in sorted(week_schedule, key=lambda x: x["day_of_week"])
        )

    done_text = texts.ONBOARDING_DONE.format(schedule=schedule_text)
    await cb.message.edit_text(done_text, reply_markup=main_menu_kb())
