from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from tg_bot import texts
from tg_bot.keyboards import goal_kb, main_menu_kb
from tg_bot.states import QuickOnboardingStates

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user_data: dict | None):
    await state.clear()
    if user_data:
        name = message.from_user.first_name
        await message.answer(texts.WELCOME_BACK.format(name=name))
        await message.answer(texts.MAIN_MENU_TITLE, reply_markup=main_menu_kb())
    else:
        # Store name from Telegram, start quick onboarding
        await state.update_data(name=message.from_user.first_name)
        await state.set_state(QuickOnboardingStates.goal)
        await message.answer(texts.WELCOME_NEW)
        await message.answer(texts.ONBOARDING_GOAL, reply_markup=goal_kb())


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
async def menu_back(callback: CallbackQuery):
    await callback.message.edit_text(texts.MAIN_MENU_TITLE, reply_markup=main_menu_kb())
    await callback.answer()


@router.callback_query(lambda cb: cb.data == "menu_video")
async def menu_video(callback: CallbackQuery):
    await callback.message.edit_text("📹 Отправь видео упражнения!")
    await callback.answer()
