import logging
import re
from typing import Tuple, List, Dict, Any, Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import db

logger = logging.getLogger(__name__)

def normalize_telegram_channel_id(ch_id: str) -> str:
    """Telegram kanal ID yoki username'ini tozalash va to'g'ri formatga keltirish"""
    cleaned = (ch_id or "").strip()
    if not cleaned:
        return ""

    # Agar raqamli ID bo'lsa (-100123... yoki 123...)
    if cleaned.startswith("-100") and cleaned[4:].isdigit():
        return cleaned
    if cleaned.startswith("-") and cleaned[1:].isdigit():
        return cleaned
    if cleaned.isdigit():
        return f"-100{cleaned}"

    # Agar havola bo'lsa (https://t.me/kino_olami yoki t.me/kino_olami)
    cleaned = re.sub(r'^(https?://)?(www\.)?t\.me/', '', cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.rstrip('/')

    # Agar xususiy havola bo'lsa (+Abcdef...)
    if cleaned.startswith("+") or "joinchat" in cleaned:
        return cleaned

    if not cleaned.startswith("@"):
        cleaned = f"@{cleaned}"
    return cleaned

def normalize_instagram_link(raw: str) -> Tuple[str, str]:
    """Instagram sahifasini username va to'liq havolaga aylantirish"""
    cleaned = (raw or "").strip()
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        url = cleaned
        # Username ajratib olish
        match = re.search(r'instagram\.com/([a-zA-Z0-9_\.\-]+)', cleaned)
        username = f"@{match.group(1)}" if match else cleaned
        return username, url
    else:
        un = cleaned.lstrip("@").strip()
        url = f"https://www.instagram.com/{un}/"
        return f"@{un}", url

def normalize_youtube_link(raw: str) -> Tuple[str, str]:
    """YouTube kanal havolasini to'g'rilash"""
    cleaned = (raw or "").strip()
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned, cleaned
    else:
        un = cleaned.strip()
        if not un.startswith("@"):
            un = f"@{un}"
        url = f"https://www.youtube.com/{un}"
        return un, url

async def check_user_channels_subscription(bot: Bot, user_id: int) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Foydalanuvchining majburiy homiylarga (Telegram, Instagram, YouTube) a'zoligini tekshirish.
    Adminlar va Premium foydalanuvchilar tekshiruvdan to'liq ozod etiladi!
    """
    # 1. Admin tekshiruvi
    if await db.is_admin(user_id):
        return True, []

    # 2. Premium tekshiruvi (Premium foydalanuvchilar reklamasiz/majburiy a'zoliksiz foydalanadi)
    if await db.is_user_premium(user_id):
        return True, []

    # 3. Bazadagi majburiy kanallar va homiylar ro'yxati
    channels = await db.get_required_channels()
    if not channels:
        return True, []

    unjoined_telegram = []

    for ch in channels:
        ch_type = ch.get("channel_type", "telegram").lower()

        # Instagram va YouTube Telegram Bot API orqali a'zolarni tekshira olmaydi.
        # Ular foydalanuvchiga tugma sifatida beriladi va bosish uchun ko'rsatiladi.
        if ch_type in ["instagram", "youtube"]:
            continue

        # Telegram kanal a'zoligini tekshirish
        raw_id = ch["channel_id"]
        normalized_id = normalize_telegram_channel_id(raw_id)

        # Agar xususiy havola bo'lsa (+...) va bot raqamli ID'ga ega bo'lmasa, get_chat_member xato beradi
        if normalized_id.startswith("+") or "joinchat" in normalized_id:
            continue

        try:
            # Raqamli bo'lsa integer formatda uzatish
            if normalized_id.startswith("-") and normalized_id[1:].isdigit():
                chat_target = int(normalized_id)
            else:
                chat_target = normalized_id

            member = await bot.get_chat_member(chat_id=chat_target, user_id=user_id)
            status = getattr(member, "status", "")

            if status in ["creator", "administrator", "member"]:
                pass  # A'zo bo'lgan!
            elif status == "restricted":
                is_member = getattr(member, "is_member", True)
                if not is_member:
                    unjoined_telegram.append(ch)
            else:
                # "left", "kicked", yoki a'zo emas
                unjoined_telegram.append(ch)

        except Exception as e:
            err_msg = str(e).lower()
            logger.warning(f"Kanalga a'zolikni tekshirishda xatolik ({raw_id} -> {normalized_id}): {e}")
            # Agar bot kanalda admin bo'lmasa yoki kanal topilmasa:
            # ("member list is inaccessible", "chat not found", "bot is not a member", "chat_admin_required")
            # Bunday holatda bot o'z xatosi sababli oddiy foydalanuvchini bloklamasligi kerak!
            if any(term in err_msg for term in ["inaccessible", "not found", "not a member", "admin"]):
                logger.error(f"⚠️ Bot kanalda admin emas yoki kanal mavjud emas: {raw_id}. Foydalanuvchi bloklanmadi.")
                pass
            else:
                unjoined_telegram.append(ch)

    if unjoined_telegram:
        # Foydalanuvchiga barcha homiylarni (Telegram, Instagram, YouTube) ko'rsatamiz
        return False, channels
    return True, []

def get_subscription_keyboard(channels: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Homiy kanallarga a'zo bo'lish tugmalari va tekshirish tugmasi"""
    buttons = []
    for idx, ch in enumerate(channels, 1):
        ch_type = ch.get("channel_type", "telegram").lower()
        name = ch.get("channel_name") or f"Homiy #{idx}"
        link = ch.get("invite_link") or ""

        if ch_type == "instagram":
            btn_text = f"📸 {name} (Instagram)"
            if not link:
                raw = ch["channel_id"].lstrip("@")
                link = f"https://www.instagram.com/{raw}/"
        elif ch_type == "youtube":
            btn_text = f"🔴 {name} (YouTube)"
            if not link:
                raw = ch["channel_id"]
                link = raw if raw.startswith("http") else f"https://www.youtube.com/{raw}"
        else:
            btn_text = f"📢 {name} ga a'zo bo'lish"
            if not link:
                raw_id = normalize_telegram_channel_id(ch["channel_id"])
                if raw_id.startswith("@"):
                    link = f"https://t.me/{raw_id.lstrip('@')}"
                else:
                    link = f"https://t.me/{raw_id}"

        buttons.append([InlineKeyboardButton(text=btn_text, url=link)])

    buttons.append([
        InlineKeyboardButton(text="✅ A'zo bo'ldim / Tekshirish", callback_data="check_sub_status")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
