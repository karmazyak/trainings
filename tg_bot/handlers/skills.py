"""Skill handlers: structured actions with plan caching."""

import logging
from html import escape

import httpx
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from tg_bot import prompts, texts
from tg_bot.api_client import AreteAPI
from tg_bot.db import get_user as get_local_user, set_conversation_id
from tg_bot.keyboards import after_ask_kb, after_skill_kb, cancel_kb, difficulty_kb, main_menu_kb, session_action_kb, skip_or_cancel_kb
from tg_bot.science_facts import get_random_fact
from tg_bot.states import FitnessTestStates, SessionFeedbackStates, SkillStates
from tg_bot.utils import days_word as _days_word, send_long as _send_long, send_long_new

logger = logging.getLogger(__name__)
router = Router()

# Set of user IDs currently generating plans (prevent concurrent requests)
_generating: set[str] = set()

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


def _streak_text(current: int, max_streak: int, just_broken: bool = False) -> str:
    """Build streak display text."""
    if just_broken and max_streak > 1:
        return texts.STREAK_BROKEN.format(max=max_streak, days_word=_days_word(max_streak))

    if current == 0:
        return ""

    dw = _days_word(current)

    # Check milestones
    if current == 7:
        return texts.STREAK_MILESTONE_7
    if current == 14:
        return texts.STREAK_MILESTONE_14
    if current == 30:
        return texts.STREAK_MILESTONE_30

    # New record
    if current == max_streak and current > 1:
        return texts.STREAK_NEW_RECORD.format(current=current, days_word=dw)

    # Normal display
    if max_streak > current:
        return texts.STREAK_WITH_RECORD.format(current=current, max=max_streak, days_word=dw)
    return texts.STREAK_DISPLAY.format(current=current, days_word=dw)


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
        await status_msg.edit_text(texts.SERVER_ERROR, reply_markup=main_menu_kb())
        return
    except Exception:
        logger.exception("Plan error")
        await status_msg.edit_text(texts.SERVER_ERROR, reply_markup=main_menu_kb())
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
        await status_msg.edit_text(texts.SERVER_ERROR, reply_markup=main_menu_kb())
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


# ── "My Day" — schedule-based today view ─────────────────


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
        await status_msg.edit_text(texts.SERVER_ERROR, reply_markup=main_menu_kb())
        return

    workout = result.get("workout")
    meal = result.get("meal")
    day_label = result.get("day_label", "")
    session_id = result.get("session_id")
    session_status = result.get("session_status")
    session_type = result.get("session_type")
    session_title = result.get("session_title")

    if not workout and not meal:
        await status_msg.edit_text(texts.MY_DAY_NO_PLANS, reply_markup=main_menu_kb())
        return

    # Rest day — show a different, calming view
    if session_type == "rest":
        rest_text = texts.MY_DAY_REST.format(day_label=day_label)
        if meal:
            rest_text += f"\n\n<b>🥗 Питание</b>\n{meal}"
        await _send_long(status_msg, rest_text, reply_markup=main_menu_kb())
        return

    # Handle already completed/skipped sessions
    if session_status == "completed":
        await status_msg.edit_text(
            texts.MY_DAY_COMPLETED.format(day_label=day_label),
            reply_markup=main_menu_kb(),
        )
        return

    if session_status == "skipped":
        await status_msg.edit_text(
            texts.MY_DAY_SKIPPED.format(day_label=day_label),
            reply_markup=main_menu_kb(),
        )
        return

    # Build the day view
    parts = []
    header = f"📅 <b>{day_label}"
    if session_title:
        header += f" — {session_title}"
    header += "</b>\n"

    # Show streak in header
    current_streak = result.get("current_streak", 0)
    max_streak = result.get("max_streak", 0)
    if current_streak > 0:
        dw = _days_word(current_streak)
        header += f"🔥 Серия: {current_streak} {dw}\n"

    parts.append(header)

    if workout:
        parts.append("<b>🏋️ Тренировка</b>\n" + workout)

    if meal:
        parts.append("<b>🥗 Питание</b>\n" + meal)

    text = "\n\n".join(parts)

    # Show complete/skip buttons if there's a training session
    if session_id and session_status == "scheduled":
        kb = session_action_kb(session_id)
    else:
        kb = main_menu_kb()

    await _send_long(status_msg, text, reply_markup=kb)


# ── Session complete/skip handlers ───────────────────────


@router.callback_query(lambda cb: cb.data and cb.data.startswith("session_done_"))
async def handle_session_complete(cb: CallbackQuery, state: FSMContext, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await cb.answer()
        return
    await cb.answer()

    short_id = cb.data.replace("session_done_", "")

    try:
        result = await api.complete_session(short_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            await cb.message.edit_text(
                "⏰ Эта тренировка уже неактуальна.\nНажми «📅 Мой день» для актуальной.",
                reply_markup=main_menu_kb(),
            )
        else:
            logger.exception("Failed to complete session")
            await cb.message.edit_text(texts.SERVER_ERROR, reply_markup=main_menu_kb())
        return
    except Exception:
        logger.exception("Failed to complete session")
        await cb.message.edit_text(texts.SERVER_ERROR, reply_markup=main_menu_kb())
        return

    # Build completion message with streak + science fact in one message
    current_streak = result.get("current_streak", 0)
    max_streak = result.get("max_streak", 0)
    streak_broken = result.get("streak_just_broken", False)

    parts = [texts.SESSION_COMPLETED]
    streak_msg = _streak_text(current_streak, max_streak, streak_broken)
    if streak_msg:
        parts.append(streak_msg)

    # Add science fact inline
    local_user = await get_local_user(cb.from_user.id)
    training_style = local_user.get("training_style") if local_user else None
    fact = get_random_fact(training_style=training_style)
    parts.append(f"{texts.SCIENCE_FACT_HEADER}\n{fact}")

    await cb.message.edit_text("\n\n".join(parts))

    # Ask for difficulty rating (second message with keyboard)
    await cb.message.answer(
        texts.SESSION_RATE_DIFFICULTY,
        reply_markup=difficulty_kb(short_id),
    )


@router.callback_query(lambda cb: cb.data and cb.data.startswith("session_skip_"))
async def handle_session_skip(cb: CallbackQuery, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await cb.answer()
        return
    await cb.answer()

    short_id = cb.data.replace("session_skip_", "")

    try:
        await api.skip_session(short_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            await cb.message.edit_text(
                "⏰ Эта тренировка уже неактуальна.\nНажми «📅 Мой день» для актуальной.",
                reply_markup=main_menu_kb(),
            )
        else:
            logger.exception("Failed to skip session")
            await cb.message.edit_text(texts.SERVER_ERROR, reply_markup=main_menu_kb())
        return
    except Exception:
        logger.exception("Failed to skip session")
        await cb.message.edit_text(texts.SERVER_ERROR, reply_markup=main_menu_kb())
        return

    await cb.message.edit_text(texts.SESSION_SKIPPED, reply_markup=main_menu_kb())


@router.callback_query(lambda cb: cb.data and cb.data.startswith("diff_"))
async def handle_difficulty_rating(cb: CallbackQuery, state: FSMContext, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await cb.answer()
        return
    await cb.answer()

    # Parse: diff_{session_short_id}_{rating}
    # Format: "diff_{32hex}_{1-5}"
    raw = cb.data[5:]  # strip "diff_"
    if len(raw) < 34 or raw[32] != "_":  # 32 hex + underscore + rating
        return
    short_id = raw[:32]
    try:
        rating = int(raw[33:])
        if not 1 <= rating <= 5:
            return
    except ValueError:
        return

    try:
        await api.complete_session(short_id, difficulty_rating=rating)
    except Exception:
        logger.exception("Failed to save difficulty")

    # Ask for text feedback
    await state.update_data(session_short_id=short_id)
    await state.set_state(SessionFeedbackStates.collecting_feedback)
    await cb.message.edit_text(texts.SESSION_FEEDBACK_ASK, reply_markup=skip_or_cancel_kb())


@router.message(SessionFeedbackStates.collecting_feedback, F.text)
async def handle_session_feedback_text(message: Message, state: FSMContext, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await message.answer(texts.NOT_REGISTERED)
        return

    data = await state.get_data()
    short_id = data.get("session_short_id")
    await state.clear()

    text = message.text.strip()
    if text.lower() in ("/skip", "skip", "пропустить"):
        await message.answer(texts.SESSION_DIFFICULTY_SAVED, reply_markup=main_menu_kb())
        return

    if short_id:
        try:
            await api.complete_session(short_id, feedback=text)
        except Exception:
            logger.exception("Failed to save session feedback")
            await message.answer("⚠️ Не удалось сохранить отзыв. Попробуй позже.", reply_markup=main_menu_kb())
            return

    await message.answer(texts.SESSION_FEEDBACK_SAVED, reply_markup=main_menu_kb())


# ── Week Schedule View ────────────────────────────────────

DAY_NAMES_RU = {
    1: "Пн", 2: "Вт", 3: "Ср", 4: "Чт", 5: "Пт", 6: "Сб", 7: "Вс",
}

STATUS_ICONS = {
    "scheduled": "⬜",
    "completed": "✅",
    "skipped": "⏭",
}


@router.callback_query(lambda cb: cb.data == "skill_week_schedule")
async def skill_week_schedule(cb: CallbackQuery, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await cb.answer()

    status_msg = await cb.message.edit_text("⏳ Загружаю расписание...")

    try:
        result = await api.get_week_schedule(user_data["backend_user_id"])
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            await status_msg.edit_text(
                "📅 Расписание ещё не создано.\n\n"
                "Нажми «🏋️ Программа» в меню, чтобы создать расписание на неделю.",
                reply_markup=main_menu_kb(),
            )
            return
        logger.exception("Week schedule HTTP error %d", e.response.status_code)
        await status_msg.edit_text(texts.SERVER_ERROR, reply_markup=main_menu_kb())
        return
    except Exception:
        logger.exception("Week schedule error")
        await status_msg.edit_text(texts.SERVER_ERROR, reply_markup=main_menu_kb())
        return

    sessions = result.get("sessions", [])
    stats = result.get("stats", {})

    parts = ["<b>📋 Расписание на неделю</b>\n"]
    for s in sessions:
        day = DAY_NAMES_RU.get(s["day_of_week"], "?")
        icon = STATUS_ICONS.get(s["status"], "⬜")
        title = s.get("title") or ("Отдых" if s["session_type"] == "rest" else "Тренировка")
        if s["session_type"] == "rest":
            parts.append(f"{icon} <b>{day}</b> — 🧘 {title}")
        else:
            parts.append(f"{icon} <b>{day}</b> — {title}")

    # Stats line
    total = stats.get("total_training", 0)
    completed = stats.get("completed", 0)
    skipped = stats.get("skipped", 0)
    if total:
        parts.append(f"\n📊 {completed}/{total} выполнено" + (f", {skipped} пропущено" if skipped else ""))

    text = "\n".join(parts)
    await status_msg.edit_text(text, reply_markup=main_menu_kb())


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
        await cb.message.edit_text(texts.SERVER_ERROR, reply_markup=main_menu_kb())
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
    uid = user_data["backend_user_id"]

    # Prevent concurrent plan generation
    if uid in _generating:
        await cb.message.edit_text("⏳ План уже генерируется, подожди...")
        return

    # Check profile for meal skills
    if skill_key in NEEDS_PROFILE:
        ready = await _check_profile_for_meal(cb, state, api, user_data, skill_key)
        if not ready:
            return

    _generating.add(uid)
    try:
        await _run_cached_skill(cb, api, user_data, skill_key, force=False)
    finally:
        _generating.discard(uid)


@router.callback_query(lambda cb: cb.data in FORCE_REGEN)
async def handle_force_regen(cb: CallbackQuery, state: FSMContext, api: AreteAPI, user_data: dict | None):
    """Force-regenerate a plan (user clicked '🔄 Новая ...')."""
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await cb.answer()

    original_skill = FORCE_REGEN[cb.data]
    uid = user_data["backend_user_id"]

    if uid in _generating:
        await cb.message.edit_text("⏳ План уже генерируется, подожди...")
        return

    if original_skill in NEEDS_PROFILE:
        ready = await _check_profile_for_meal(cb, state, api, user_data, original_skill)
        if not ready:
            return

    _generating.add(uid)
    try:
        await _run_cached_skill(cb, api, user_data, original_skill, force=True)
    finally:
        _generating.discard(uid)


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

    if not height_cm:
        await message.answer("⚠️ Рост не был сохранён. Попробуй ещё раз через меню.", reply_markup=main_menu_kb())
        return

    # Update backend profile with height/weight
    try:
        await api.update_user(
            user_data["backend_user_id"],
            {"height_cm": height_cm, "weight_kg": weight},
        )
    except Exception:
        logger.exception("Failed to update profile")
        await message.answer(texts.SERVER_ERROR, reply_markup=main_menu_kb())
        return

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
            await message.answer(texts.SERVER_ERROR, reply_markup=main_menu_kb())
            return

        content = result.get("content", "")
        agent_label = texts.AGENT_LABELS.get(agent if agent != "auto" else "both", "🏛 Arete")
        text = f"<b>{escape(agent_label)}</b>  <i>{texts.PLAN_FRESH}</i>\n\n{content}"
        kb = after_skill_kb(repeat_cb, repeat_label)

        await send_long_new(message, text, reply_markup=kb)
    else:
        await message.answer("Готово! Используй меню для генерации планов.", reply_markup=main_menu_kb())


# ── Fitness Test ──────────────────────────────────────────


@router.callback_query(lambda cb: cb.data == "skill_fitness_test")
async def fitness_test_start(cb: CallbackQuery, state: FSMContext, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await cb.answer()
    await state.set_state(FitnessTestStates.pushups)
    await cb.message.edit_text(texts.FITNESS_TEST_INTRO)


@router.message(FitnessTestStates.pushups, F.text)
async def fitness_test_pushups(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    if text in ("/skip", "skip", "пропустить"):
        await state.clear()
        await message.answer(texts.FITNESS_TEST_SKIPPED, reply_markup=main_menu_kb())
        return
    try:
        pushups = int(text)
        if not 0 <= pushups <= 200:
            raise ValueError
    except ValueError:
        await message.answer("Введи число от 0 до 200:")
        return
    await state.update_data(pushups=pushups)
    await state.set_state(FitnessTestStates.plank)
    await message.answer(texts.FITNESS_TEST_PLANK)


@router.message(FitnessTestStates.plank, F.text)
async def fitness_test_plank(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    if text in ("/skip", "skip", "пропустить"):
        await state.clear()
        await message.answer(texts.FITNESS_TEST_SKIPPED, reply_markup=main_menu_kb())
        return
    try:
        plank = int(text)
        if not 0 <= plank <= 600:
            raise ValueError
    except ValueError:
        await message.answer("Введи число секунд от 0 до 600:")
        return
    await state.update_data(plank=plank)
    await state.set_state(FitnessTestStates.squats)
    await message.answer(texts.FITNESS_TEST_SQUATS)


@router.message(FitnessTestStates.squats, F.text)
async def fitness_test_squats(message: Message, state: FSMContext, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await message.answer(texts.NOT_REGISTERED)
        return
    text = message.text.strip().lower()
    if text in ("/skip", "skip", "пропустить"):
        await state.clear()
        await message.answer(texts.FITNESS_TEST_SKIPPED, reply_markup=main_menu_kb())
        return
    try:
        squats = int(text)
        if not 0 <= squats <= 200:
            raise ValueError
    except ValueError:
        await message.answer("Введи число от 0 до 200:")
        return

    data = await state.get_data()
    await state.clear()

    pushups = data.get("pushups", 0)
    plank = data.get("plank", 0)

    # Save to backend
    from datetime import date as date_cls
    try:
        await api.update_user(user_data["backend_user_id"], {
            "test_pushups": pushups,
            "test_plank_sec": plank,
            "test_squats": squats,
            "fitness_test_date": date_cls.today().isoformat(),
        })
    except Exception:
        logger.exception("Failed to save fitness test")

    await message.answer(
        texts.FITNESS_TEST_DONE.format(pushups=pushups, plank=plank, squats=squats),
        reply_markup=main_menu_kb(),
    )


# ── Ask Trainer / Dietologist ────────────────────────────


# ── Unified Question (v2 — auto-routing) ─────────────────


@router.callback_query(lambda cb: cb.data == "ask_question")
async def ask_question_start(cb: CallbackQuery, state: FSMContext, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await state.set_state(SkillStates.asking_question)
    await cb.message.edit_text(
        "💬 Задай любой вопрос — про тренировки, питание, технику:",
        reply_markup=cancel_kb(),
    )
    await cb.answer()


@router.message(SkillStates.asking_question, F.text)
async def ask_question_message(message: Message, state: FSMContext, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await message.answer(texts.NOT_REGISTERED)
        return
    await state.clear()
    await _run_ask_skill(message, api, user_data, agent="auto", repeat_callback="ask_question")


# ── Ask Trainer / Dietologist (legacy, still works) ──────


@router.callback_query(lambda cb: cb.data == "skill_ask_trainer")
async def ask_trainer_start(cb: CallbackQuery, state: FSMContext, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await state.set_state(SkillStates.asking_trainer)
    await cb.message.edit_text(texts.ASK_TRAINER_PROMPT, reply_markup=cancel_kb())
    await cb.answer()


@router.callback_query(lambda cb: cb.data == "skill_ask_dietologist")
async def ask_dietologist_start(cb: CallbackQuery, state: FSMContext, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await state.set_state(SkillStates.asking_dietologist)
    await cb.message.edit_text(texts.ASK_DIETOLOGIST_PROMPT, reply_markup=cancel_kb())
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
