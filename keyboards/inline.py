import math
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from typing import List, Dict, Any, Optional
from config import SUPPORT_USERNAME, WEBAPP_URL

def get_category_keyboard() -> InlineKeyboardMarkup:
    """Kategoriyalarni tanlash menyusi"""
    buttons = [
        [
            InlineKeyboardButton(text="🎬 Filmlar", callback_data="cat:kino"),
            InlineKeyboardButton(text="📺 Seriallar", callback_data="cat:serial")
        ],
        [
            InlineKeyboardButton(text="⛩ Anime", callback_data="cat:anime"),
            InlineKeyboardButton(text="🎭 Koreys & Xitoy Dramalar", callback_data="cat:drama")
        ],
        [
            InlineKeyboardButton(text="🔍 Kod orqali qidirish", callback_data="action:search_code")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_category_items_keyboard(category: str, items: List[Dict[str, Any]], page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Kategoriya ichidagi medialar va sahifalash"""
    keyboard = []
    
    # Har bir media uchun tugma
    for item in items:
        premium_badge = "⭐ " if item.get("is_premium") else "🆓 "
        text = f"{premium_badge}{item['title']} [{item['code']}]"
        keyboard.append([
            InlineKeyboardButton(text=text, callback_data=f"view:{item['code']}")
        ])

    # Sahifalash (Pagination)
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"page:{category}:{page-1}"))
    
    nav_row.append(InlineKeyboardButton(text=f"📄 {page}/{max(1, total_pages)}", callback_data="noop"))
    
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"page:{category}:{page+1}"))
    
    keyboard.append(nav_row)
    
    # Orqaga qaytish
    keyboard.append([
        InlineKeyboardButton(text="🔙 Kategoriyalarga qaytish", callback_data="cat:back")
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_media_view_keyboard(
    code: str,
    is_premium: bool,
    user_is_premium: bool,
    episodes: List[Dict[str, Any]] = None,
    is_fav: bool = False,
    bot_username: str = "FlixUzCinemaBot",
    ep_page: int = 1,
    page_size: int = 15
) -> InlineKeyboardMarkup:
    """Media kartochkasi tugmalari (poster, serial qismlari, sahifalash, sevimlilar, ulashish)"""
    buttons = []
    
    if is_premium and not user_is_premium:
        buttons.append([
            InlineKeyboardButton(text="⭐ Ushbu film faqat Premium uchun!", callback_data="noop")
        ])
        buttons.append([
            InlineKeyboardButton(text="💎 Premium obuna olish", callback_data="action:get_premium")
        ])
    else:
        if episodes and len(episodes) > 0:
            total_eps = len(episodes)
            total_pages = max(1, math.ceil(total_eps / page_size))
            ep_page = max(1, min(ep_page, total_pages))

            start_idx = (ep_page - 1) * page_size
            end_idx = start_idx + page_size
            page_episodes = episodes[start_idx:end_idx]

            # Qismlar tugmalari (har qatorda 3 tadan)
            row = []
            for ep in page_episodes:
                ep_num = ep['episode_num']
                ep_is_prem = bool(ep.get('is_premium', 0))
                if ep_is_prem and not user_is_premium:
                    badge = f"🔒 {ep_num}-qism ⭐"
                elif ep_is_prem and user_is_premium:
                    badge = f"⭐ {ep_num}-qism"
                else:
                    badge = f"▶️ {ep_num}-qism"
                
                row.append(InlineKeyboardButton(text=badge, callback_data=f"ep_dl:{ep['id']}"))
                if len(row) == 3:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)

            # Agar qismlar bir sahifadan ko'p bo'lsa, sahifalash tugmalari
            if total_pages > 1:
                pag_row = []
                if ep_page > 1:
                    pag_row.append(InlineKeyboardButton(text="◀️ Oldingi", callback_data=f"ep_pg:{code}:{ep_page - 1}"))
                pag_row.append(InlineKeyboardButton(text=f"📄 {ep_page}/{total_pages}", callback_data="noop"))
                if ep_page < total_pages:
                    pag_row.append(InlineKeyboardButton(text="Keyingi ▶️", callback_data=f"ep_pg:{code}:{ep_page + 1}"))
                buttons.append(pag_row)
        else:
            buttons.append([
                InlineKeyboardButton(text="🎬 Filmni tomosha qilish", callback_data=f"download:{code}")
            ])

    # Sevimlilar va Do'stlarga ulashish qatori
    fav_btn_text = "💔 Sevimlilardan o'chirish" if is_fav else "❤️ Sevimlilarga qo'shish"
    fav_cb = f"fav_del:{code}" if is_fav else f"fav_add:{code}"
    
    share_url = f"https://t.me/share/url?url=https://t.me/{bot_username}?start={code}&text=Zo%27r%20film%20topdim!%20Tomosha%20qiling!"
    
    buttons.append([
        InlineKeyboardButton(text=fav_btn_text, callback_data=fav_cb),
        InlineKeyboardButton(text="🔗 Do'stlarga ulashish", url=share_url)
    ])

    buttons.append([
        InlineKeyboardButton(text="🔙 Orqaga", callback_data="cat:back")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_episode_player_keyboard(media_code: str, prev_id: Optional[int], next_id: Optional[int]) -> InlineKeyboardMarkup:
    """Serial yoki anime qismi ostidagi navigatsiya tugmalari"""
    nav_row = []
    if prev_id:
        nav_row.append(InlineKeyboardButton(text="⏮ Oldingi qism", callback_data=f"ep_dl:{prev_id}"))
    if next_id:
        nav_row.append(InlineKeyboardButton(text="Keyingi qism ⏭", callback_data=f"ep_dl:{next_id}"))

    keyboard = []
    if nav_row:
        keyboard.append(nav_row)

    keyboard.append([
        InlineKeyboardButton(text="📋 Barcha qismlar / Kartochka", callback_data=f"view:{media_code}")
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Admin boshqaruv paneli tugmalari"""
    buttons = [
        [
            InlineKeyboardButton(text="📱 Admin Mini Appni ochish", web_app=WebAppInfo(url=WEBAPP_URL)),
        ],
        [
            InlineKeyboardButton(text="➕ Yangi media qo‘shish", callback_data="admin:addmedia"),
            InlineKeyboardButton(text="📦 Ommaviy qism yuklash", callback_data="admin:batchupload"),
        ],
        [
            InlineKeyboardButton(text="💰 Qismlar narxi (Threshold)", callback_data="admin:epaccess"),
            InlineKeyboardButton(text="📢 Majburiy obuna kanallari", callback_data="admin:channels"),
        ],
        [
            InlineKeyboardButton(text="🚀 Kanalga post sozlash", callback_data="admin:setpostchannel"),
            InlineKeyboardButton(text="💡 Film buyurtmalari", callback_data="admin:requests"),
        ],
        [
            InlineKeyboardButton(text="📋 Medialar ro‘yxati", callback_data="admin:medialist"),
            InlineKeyboardButton(text="🔒 Bepul/Pullik sozlash", callback_data="admin:access"),
        ],
        [
            InlineKeyboardButton(text="🗑 Media o‘chirish", callback_data="admin:deletemedia"),
            InlineKeyboardButton(text="⭐ Premium berish", callback_data="admin:grant_premium"),
        ],
        [
            InlineKeyboardButton(text="💎 Premium narx & To'lov admini", callback_data="admin:premium_settings"),
        ],
        [
            InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admin:users"),
            InlineKeyboardButton(text="📊 Umumiy statistika", callback_data="admin:stats"),
        ],
        [
            InlineKeyboardButton(text="📅 Oylik statistika", callback_data="admin:monthly"),
            InlineKeyboardButton(text="👑 Admin qo‘shish", callback_data="admin:addadmin"),
        ],
        [
            InlineKeyboardButton(text="🚫 Foydalanuvchini bloklash", callback_data="admin:blockuser"),
            InlineKeyboardButton(text="✅ Blokdan chiqarish", callback_data="admin:unblockuser"),
        ],
        [
            InlineKeyboardButton(text="❌ Adminni o‘chirish", callback_data="admin:removeadmin"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_category_select_keyboard() -> InlineKeyboardMarkup:
    """Media qo'shishda kategoriyani tanlash"""
    buttons = [
        [
            InlineKeyboardButton(text="🎬 Kino (Film)", callback_data="select_cat:kino"),
            InlineKeyboardButton(text="📺 Serial", callback_data="select_cat:serial"),
        ],
        [
            InlineKeyboardButton(text="⛩ Anime", callback_data="select_cat:anime"),
            InlineKeyboardButton(text="🎭 Drama", callback_data="select_cat:drama"),
        ],
        [
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_action")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_media_access_choice_keyboard() -> InlineKeyboardMarkup:
    """Media kirish huquqini tanlash"""
    buttons = [
        [
            InlineKeyboardButton(text="🆓 Bepul (Barcha foydalanuvchilar uchun)", callback_data="access_type:0"),
        ],
        [
            InlineKeyboardButton(text="⭐ Faqat Premium obunachilar uchun", callback_data="access_type:1"),
        ],
        [
            InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_action")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_premium_plans_keyboard(
    p_1m_uzs: str = "15 000",
    p_3m_uzs: str = "40 000",
    p_1y_uzs: str = "120 000",
    p_1m_stars: str = "75",
    p_3m_stars: str = "199",
    p_1y_stars: str = "599"
) -> InlineKeyboardMarkup:
    """Premium tariflar tugmalari (Dinamik narxlar bilan)"""
    buttons = [
        [
            InlineKeyboardButton(text=f"⭐ 1 Oylik — {p_1m_uzs} so'm / {p_1m_stars} ⭐", callback_data="plan_choice:1_month"),
        ],
        [
            InlineKeyboardButton(text=f"⭐ 3 Oylik — {p_3m_uzs} so'm / {p_3m_stars} ⭐", callback_data="plan_choice:3_months"),
        ],
        [
            InlineKeyboardButton(text=f"👑 1 Yillik VIP — {p_1y_uzs} so'm / {p_1y_stars} ⭐", callback_data="plan_choice:1_year"),
        ],
        [
            InlineKeyboardButton(text="🔄 Holatimni tekshirish", callback_data="check_premium_status")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
