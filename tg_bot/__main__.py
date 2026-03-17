import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from tg_bot.api_client import AreteAPI
from tg_bot.config import settings
from tg_bot.db import close_db, init_db
from tg_bot.handlers.chat import router as chat_router
from tg_bot.handlers.feedback import router as feedback_router
from tg_bot.handlers.onboarding import router as onboarding_router
from tg_bot.handlers.profile import router as profile_router
from tg_bot.handlers.settings import router as settings_router
from tg_bot.handlers.skills import router as skills_router
from tg_bot.handlers.start import router as start_router
from tg_bot.handlers.video import router as video_router
from tg_bot.middlewares import UserResolverMiddleware

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

    api = AreteAPI(settings.api_base_url)
    await init_db(settings.sqlite_path)

    # Check backend health
    healthy = await api.health()
    if healthy:
        logger.info("Backend is healthy at %s", settings.api_base_url)
    else:
        logger.warning("Backend is NOT reachable at %s", settings.api_base_url)

    # Register middleware
    middleware = UserResolverMiddleware(api)
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)

    # Register routers (order matters! chat_router is catch-all, must be last)
    dp.include_router(start_router)
    dp.include_router(onboarding_router)
    dp.include_router(skills_router)
    dp.include_router(feedback_router)
    dp.include_router(video_router)
    dp.include_router(profile_router)
    dp.include_router(settings_router)
    dp.include_router(chat_router)  # catch-all for text messages

    logger.info("Arete bot started! Polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await api.close()
        await close_db()
        logger.info("Arete bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
