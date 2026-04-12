from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from tg_bot import texts
from tg_bot.keyboards import cancel_kb, main_menu_kb, try_question_kb
from tg_bot.states import (
    EditProfileStates,
    FeedbackStates,
    FitnessTestStates,
    OnboardingStates,
    SessionFeedbackStates,
    SkillStates,
)

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user_data: dict | None):
    await state.clear()
    if user_data:
        name = message.from_user.first_name
        await message.answer(texts.WELCOME_BACK.format(name=name))
        await message.answer(texts.MAIN_MENU_TITLE, reply_markup=main_menu_kb())
    else:
        # Store name for later, show try-question flow (no FSM state yet)
        await state.update_data(name=message.from_user.first_name)
        await message.answer(texts.WELCOME_NEW, reply_markup=try_question_kb())


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(texts.HELP)


@router.message(Command("menu"))
async def cmd_menu(message: Message, user_data: dict | None):
    if not user_data:
        await message.answer(texts.NOT_REGISTERED)
        return
    await message.answer(texts.MAIN_MENU_TITLE, reply_markup=main_menu_kb())


@router.callback_query(lambda cb: cb.data == "menu_back")
async def menu_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(texts.MAIN_MENU_TITLE, reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(lambda cb: cb.data == "menu_video")
async def menu_video(callback: CallbackQuery):
    await callback.message.edit_text(
        "📹 Отправь видео упражнения для анализа техники.\n\n"
        "Запиши короткое видео (10-30 сек) с хорошим углом обзора.",
        reply_markup=cancel_kb(),
    )
    await callback.answer()


@router.callback_query(lambda cb: cb.data == "cancel_state")
async def cancel_state(callback: CallbackQuery, state: FSMContext):
    """Universal cancel — clears FSM state and returns to main menu."""
    await state.clear()
    await callback.message.edit_text(texts.MAIN_MENU_TITLE, reply_markup=main_menu_kb())
    await callback.answer()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Cancel current flow and return to menu."""
    current = await state.get_state()
    await state.clear()
    if current:
        await message.answer("Отменено.", reply_markup=main_menu_kb())
    else:
        await message.answer(texts.MAIN_MENU_TITLE, reply_markup=main_menu_kb())


@router.message(
    ~F.text,
    StateFilter(
        SkillStates.collecting_height,
        SkillStates.collecting_weight,
        FitnessTestStates,
        SessionFeedbackStates,
        FeedbackStates,
        EditProfileStates,
    ),
)
async def handle_non_text_in_fsm(message: Message):
    """Catch non-text messages (photos, stickers, etc.) in FSM states that expect text."""
    await message.answer("Пожалуйста, отправь текстовое сообщение.")
