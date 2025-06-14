from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.fsm.context import FSMContext
from aiogram.utils.i18n import I18n, FSMI18nMiddleware
from typing import Callable, Dict, Any

from database.database_manager import SQLiteDatabaseManager


class CustomI18nMiddleware(BaseMiddleware):
    def __init__(self, i18n: I18n):
        self.i18n = i18n
        self.fsm_i18n = FSMI18nMiddleware(i18n)
        self._cache: Dict[int, str] = {}

    async def __call__(self, handler: Callable, event: TelegramObject, data: Dict[str, Any]):
        chat_id = None

        if hasattr(event, "chat"):
            chat_id = event.chat.id
        elif hasattr(event, "message") and hasattr(event.message, "chat"):
            chat_id = event.message.chat.id

        locale = "en"
        if chat_id:
            locale = self._cache.get(chat_id)
            if not locale:
                locale = await self._get_chat_language(chat_id)
                self._cache[chat_id] = locale

        state: FSMContext = data.get("state")
        if state:
            await self.fsm_i18n.set_locale(state, locale)

        return await handler(event, data)

    async def _get_chat_language(self, chat_id: int) -> str:
        async with SQLiteDatabaseManager() as cursor:
            await cursor.execute(
                "SELECT lang FROM chat_settings WHERE chat_id = ?", (chat_id,)
            )
            result = await cursor.fetchone()
            return result[0] if result else "en"

    def clear_cache(self, chat_id: int):
        self._cache.pop(chat_id, None)