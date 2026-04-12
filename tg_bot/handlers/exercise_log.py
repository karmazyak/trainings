"""Exercise logging — manual weight/reps tracking."""

import logging
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from tg_bot import texts
from tg_bot.api_client import AreteAPI
from tg_bot.keyboards import cancel_kb, main_menu_kb, recent_exercises_kb
from tg_bot.states import LogExerciseStates

logger = logging.getLogger(__name__)
router = Router()

# Regex to parse "85 × 5 × 4" or "85x5x4" or "85 x 5 x 4" etc.
LOG_PATTERN = re.compile(r"(\d+\.?\d*)\s*[×xXхХ*]\s*(\d+)\s*[×xXхХ*]\s*(\d+)")


# ── Manual log from menu ────────────────────────────────


@router.callback_query(lambda cb: cb.data == "log_manual")
async def start_manual_log(cb: CallbackQuery, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await cb.answer()

    # Load recent exercises
    try:
        recent = await api.get_recent_exercises(user_data["backend_user_id"])
    except Exception:
        recent = []

    # Build unique exercise list
    seen = set()
    exercises = []
    for log in recent:
        name = log.get("exercise_name", "")
        label = log.get("exercise_label", name)
        if name and name not in seen:
            seen.add(name)
            exercises.append((name, label))
        if len(exercises) >= 6:
            break

    await cb.message.edit_text(
        texts.LOG_MANUAL_CHOOSE,
        reply_markup=recent_exercises_kb(exercises),
    )


@router.callback_query(lambda cb: cb.data and cb.data.startswith("logex_") and cb.data != "logex_custom")
async def handle_exercise_selected(cb: CallbackQuery, state: FSMContext):
    exercise_name = cb.data.replace("logex_", "")
    await state.update_data(log_exercise_name=exercise_name, log_exercise_label=exercise_name)
    await state.set_state(LogExerciseStates.manual_input)
    await cb.message.edit_text(
        texts.LOG_MANUAL_INPUT.format(exercise=exercise_name),
        reply_markup=cancel_kb(),
    )
    await cb.answer()


@router.callback_query(lambda cb: cb.data == "logex_custom")
async def handle_exercise_custom(cb: CallbackQuery, state: FSMContext):
    await state.set_state(LogExerciseStates.manual_exercise_name)
    await cb.message.edit_text("✏️ Напиши название упражнения:", reply_markup=cancel_kb())
    await cb.answer()


@router.message(LogExerciseStates.manual_exercise_name, F.text)
async def handle_exercise_name_input(message: Message, state: FSMContext):
    name = message.text.strip()
    # Simple normalization
    normalized = re.sub(r"\s+", "_", name.lower().strip())
    await state.update_data(log_exercise_name=normalized, log_exercise_label=name)
    await state.set_state(LogExerciseStates.manual_input)
    await message.answer(
        texts.LOG_MANUAL_INPUT.format(exercise=name),
        reply_markup=cancel_kb(),
    )


@router.message(LogExerciseStates.manual_input, F.text)
async def handle_manual_input(message: Message, state: FSMContext, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await message.answer(texts.NOT_REGISTERED)
        return

    match = LOG_PATTERN.search(message.text)
    if not match:
        await message.answer("Формат: вес × повторения × подходы\nПример: 85 × 5 × 4")
        return

    weight = float(match.group(1))
    reps = int(match.group(2))
    sets = int(match.group(3))

    data = await state.get_data()
    exercise_name = data.get("log_exercise_name", "unknown")
    exercise_label = data.get("log_exercise_label", exercise_name)
    await state.clear()

    try:
        await api.log_exercise(user_data["backend_user_id"], {
            "exercise_name": exercise_name,
            "exercise_label": exercise_label,
            "weight_kg": weight,
            "reps": reps,
            "sets": sets,
        })
    except Exception:
        logger.exception("Failed to log exercise")
        await message.answer(texts.SERVER_ERROR, reply_markup=main_menu_kb())
        return

    text = texts.LOG_SAVED.format(
        exercise=exercise_label, weight=weight, reps=reps, sets=sets,
    )
    await message.answer(text, reply_markup=main_menu_kb())


# ── Progress view ───────────────────────────────────────


@router.callback_query(lambda cb: cb.data == "show_progress")
async def show_progress(cb: CallbackQuery, api: AreteAPI, user_data: dict | None):
    if not user_data:
        await cb.message.edit_text(texts.NOT_REGISTERED)
        await cb.answer()
        return
    await cb.answer()

    try:
        recent = await api.get_recent_exercises(user_data["backend_user_id"])
    except Exception:
        recent = []

    if not recent:
        await cb.message.edit_text(
            "📊 Пока нет записей.\n\nНажми «📝 Записать» после тренировки чтобы начать трекать прогресс.",
            reply_markup=main_menu_kb(),
        )
        return

    # Group by exercise, show latest weight
    exercises = {}
    for log in recent:
        name = log.get("exercise_name", "")
        if name not in exercises:
            exercises[name] = log

    lines = ["📊 <b>Прогресс</b>\n"]
    for name, log in list(exercises.items())[:10]:
        label = log.get("exercise_label", name)
        w = log.get("weight_kg", 0)
        r = log.get("reps", 0)
        s = log.get("sets", 0)
        lines.append(f"• {label}: {w}кг × {r} × {s}")

    await cb.message.edit_text("\n".join(lines), reply_markup=main_menu_kb())
