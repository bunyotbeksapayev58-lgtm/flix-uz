import time
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from database import db

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit: float = 0.5):
        self.rate_limit = rate_limit
        self.users_last_time: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        # To'lov xabarlari (successful_payment, invoice) va pre_checkout hech qachon cheklanmaydi
        from aiogram.types import PreCheckoutQuery
        if isinstance(event, PreCheckoutQuery):
            return await handler(event, data)
        if isinstance(event, Message) and (event.successful_payment or event.invoice):
            return await handler(event, data)

        # Adminlar uchun tezlik cheklovi (throttling) qo'llanmaydi
        if await db.is_admin(user.id):
            return await handler(event, data)

        now = time.time()
        last_time = self.users_last_time.get(user.id, 0)

        # Xotirani vaqti-vaqti bilan tozalash
        if len(self.users_last_time) > 5000:
            cutoff = now - 60
            self.users_last_time = {uid: t for uid, t in self.users_last_time.items() if t > cutoff}

        if now - last_time < self.rate_limit:
            self.users_last_time[user.id] = now
            if isinstance(event, Message):
                await event.answer("⚠️ <b>Iltimos, biroz kuting!</b> (Spamdan himoya)", parse_mode="HTML")
            elif isinstance(event, CallbackQuery):
                await event.answer("⚠️ Juda tez bosyapsiz, biroz kuting!", show_alert=False)
            return

        self.users_last_time[user.id] = now
        return await handler(event, data)
