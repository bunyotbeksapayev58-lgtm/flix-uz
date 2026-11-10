import logging
from typing import Tuple, List, Dict, Any
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db

logger = logging.getLogger(__name__)

async def check_user_channels_subscription(bot: Bot, user_id: int) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Foydalanuvchining majburiy homiy kanallarga a'zoligini tekshirish.
    Adminlar va Premium foydalanuvchilar tekshiruvdan to'liq ozod etiladi!
    """
    # 1. Admin tekshiruvi
    if await db.is_admin(user_id):
        return True, []

    # 2. Premium tekshiruvi (Premium foydalanuvchilar reklamasiz/majburiy a'zoliksiz foydalanadi)
    if await db.is_user_premium(user_id):
        return True, []

    # 3. Bazadagi majburiy kanallar ro'yxati
    channels = await db.get_required_channels()
    if not channels:
        return True, []

    unjoined = []
    for ch in channels:
        ch_id = ch["channel_id"]
        try:
            member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
            if member.status not in ["member", "administrator", "creator", "restricted"]:
                unjoined.append(ch)
        except Exception as e:
            logger.warning(f"Kanalga a'zolikni tekshirishda xatolik ({ch_id}): {e}")
            unjoined.append(ch)

    if unjoined:
        return False, unjoined
    return True, []

def get_subscription_keyboard(unjoined_channels: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Homiy kanallarga a'zo bo'lish tugmalari va tekshirish tugmasi"""
    buttons = []
    for idx, ch in enumerate(unjoined_channels, 1):
        name = ch.get("channel_name") or f"Homiy Kanal #{idx}"
        link = ch.get("invite_link")
        if not link:
            ch_raw = ch["channel_id"].lstrip("@")
            link = f"https://t.me/{ch_raw}"
        buttons.append([InlineKeyboardButton(text=f"📢 {name} ga a'zo bo'lish", url=link)])

    buttons.append([
        InlineKeyboardButton(text="✅ A'zo bo'ldim / Tekshirish", callback_data="check_sub_status")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
