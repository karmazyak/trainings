import asyncio
import logging

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from tg_bot.api_client import AreteAPI
from tg_bot.config import settings
from tg_bot.db import close_db, init_db
from tg_bot.handlers.chat import router as chat_router
from tg_bot.handlers.exercise_log import router as exercise_log_router
from tg_bot.handlers.feedback import router as feedback_router
from tg_bot.handlers.onboarding import router as onboarding_router
from tg_bot.handlers.profile import router as profile_router
from tg_bot.handlers.settings import router as settings_router
from tg_bot.handlers.situation import router as situation_router
from tg_bot.handlers.skills import router as skills_router
from tg_bot.handlers.start import router as start_router
from tg_bot.handlers.video import router as video_router
from tg_bot.middlewares import ThrottlingMiddleware, UserResolverMiddleware
from tg_bot.scheduler import scheduler_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Starting Arete bot...")

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode="HTML"),
    )
    dp = Dispatcher(storage=MemoryStorage())

    api = AreteAPI(settings.api_base_url, api_key=settings.api_secret_key)
    await init_db(settings.sqlite_path)

    # Check backend health
    healthy = await api.health()
    if healthy:
        logger.info("Backend is healthy at %s", settings.api_base_url)
    else:
        logger.warning("Backend is NOT reachable at %s", settings.api_base_url)

    # Global error handler — user always gets a friendly message
    @dp.error()
    async def global_error_handler(event: ErrorEvent):
        logger.exception("Unhandled error: %s", event.exception)
        try:
            update = event.update
            chat_id = None
            if update.message:
                chat_id = update.message.chat.id
            elif update.callback_query:
                chat_id = update.callback_query.message.chat.id
                try:
                    await update.callback_query.answer()
                except Exception:
                    pass
            if chat_id:
                from tg_bot.keyboards import main_menu_kb
                await bot.send_message(
                    chat_id,
                    "⚠️ Что-то пошло не так. Попробуй ещё раз.",
                    reply_markup=main_menu_kb(),
                )
        except Exception:
            logger.exception("Failed to send error message to user")

    # Register middleware (throttling first, then user resolver)
    throttle = ThrottlingMiddleware(rate_limit=3, window=5.0)
    dp.message.middleware(throttle)
    dp.callback_query.middleware(throttle)

    resolver = UserResolverMiddleware(api)
    dp.message.middleware(resolver)
    dp.callback_query.middleware(resolver)

    # Register routers (order matters! chat_router is catch-all, must be last)
    dp.include_router(start_router)
    dp.include_router(onboarding_router)
    dp.include_router(situation_router)
    dp.include_router(exercise_log_router)
    dp.include_router(skills_router)
    dp.include_router(feedback_router)
    dp.include_router(video_router)
    dp.include_router(profile_router)
    dp.include_router(settings_router)
    dp.include_router(chat_router)  # catch-all for text messages

    # Start daily reminder scheduler in background
    reminder_task = asyncio.create_task(scheduler_loop(bot, api))

    logger.info("Arete bot started! Polling...")
    try:
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        await api.close()
        await close_db()
        logger.info("Arete bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
