from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from tg_bot.api_client import AreteAPI
from tg_bot.db import get_user


class UserResolverMiddleware(BaseMiddleware):
    """Resolve tg_id -> backend user data and inject api client into every handler."""

    def __init__(self, api: AreteAPI) -> None:
        self.api = api

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["api"] = self.api

        user = getattr(event, "from_user", None)
        if user:
            user_data = await get_user(user.id)
            data["user_data"] = user_data
        else:
            data["user_data"] = None

        return await handler(event, data)
