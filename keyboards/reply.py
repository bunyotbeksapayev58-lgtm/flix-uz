from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo
from config import WEBAPP_URL

def get_main_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Asosiy menyu tugmalari (Master UI/UX)"""
    buttons = [
        [KeyboardButton(text="🎬 Filmlar"), KeyboardButton(text="📺 Seriallar")],
        [KeyboardButton(text="🇰🇷 Dramalar"), KeyboardButton(text="🍥 Anime")],
        [KeyboardButton(text="🔍 Film qidirish"), KeyboardButton(text="🔢 Kod orqali topish")],
        [KeyboardButton(text="🔥 Mashhur filmlar"), KeyboardButton(text="🆕 Yangi qo‘shilganlar")],
        [KeyboardButton(text="❤️ Sevimlilar"), KeyboardButton(text="📚 Mening tarixim")],
        [KeyboardButton(text="💡 Film so‘rash"), KeyboardButton(text="⭐ Premium")],
        [KeyboardButton(text="👤 Profil"), KeyboardButton(text="⚙️ Sozlamalar")],
    ]
    if is_admin:
        buttons.append([
            KeyboardButton(text="📱 Admin Mini App", web_app=WebAppInfo(url=WEBAPP_URL)),
            KeyboardButton(text="⚙️ Admin panel")
        ])

    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        persistent=True
    )

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Bekor qilish tugmasi"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Bekor qilish")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
