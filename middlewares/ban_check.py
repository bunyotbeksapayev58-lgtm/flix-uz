from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from database import db

class BanCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        # Bloklanganlikni tekshirish (Yangi foydalanuvchini ro'yxatga olish /start da amalga oshiriladi)
        is_blocked = await db.is_user_blocked(user.id)
        if is_blocked:
            if isinstance(event, Message):
                await event.answer("🚫 Kechirasiz, siz bot ma'muriyati tomonidan bloklangansiz!")
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 Siz bloklangansiz!", show_alert=True)
            return

        return await handler(event, data)
