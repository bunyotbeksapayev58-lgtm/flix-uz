from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.fsm.context import FSMContext
from database import db
from keyboards import get_main_keyboard, get_category_keyboard, get_media_view_keyboard
from handlers.movies import render_media_card

router = Router()

CANCEL_WORDS = {
    "❌ bekor qilish", "bekor qilish", "bekor", "cancel", "/cancel",
    "❌ bekor", "🔙 bekor qilish", "🔙 orqaga", "orqaga", "chiqish", "/stop", "stop"
}

def is_cancel_message(text: str | None) -> bool:
    if not text:
        return False
    return text.strip().lower() in CANCEL_WORDS

@router.message(Command("cancel"))
@router.message(F.text.func(is_cancel_message))
async def cancel_handler(message: Message, state: FSMContext):
    """Har qanday jarayonni bekor qilish"""
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()

    try:
        from handlers.media_mgmt import cancel_batch_session
        cancel_batch_session(message.from_user.id)
    except Exception:
        pass

    is_admin = await db.is_admin(message.from_user.id)
    await message.answer("❌ Jarayon bekor qilindi.", reply_markup=get_main_keyboard(is_admin))

@router.callback_query(F.data == "cancel_action")
async def cancel_callback(call: CallbackQuery, state: FSMContext):
    """Inline tugmalardagi bekor qilish / orqaga qaytish"""
    await state.clear()
    try:
        from handlers.media_mgmt import cancel_batch_session
        cancel_batch_session(call.from_user.id)
    except Exception:
        pass

    is_admin = await db.is_admin(call.from_user.id)
    try:
        await call.answer("❌ Bekor qilindi")
    except Exception:
        pass

    if is_admin:
        from keyboards.inline import get_admin_keyboard
        try:
            await call.message.edit_text(
                "👑 <b>Admin boshqaruv paneli</b>\n\nQuyidagi boshqaruv bo'limlaridan birini tanlang:",
                parse_mode="HTML",
                reply_markup=get_admin_keyboard()
            )
        except Exception:
            try:
                await call.message.delete()
            except Exception:
                pass
            await call.message.answer(
                "👑 <b>Admin boshqaruv paneli</b>\n\nQuyidagi boshqaruv bo'limlaridan birini tanlang:",
                parse_mode="HTML",
                reply_markup=get_admin_keyboard()
            )
        await call.message.answer("Asosiy menyu:", reply_markup=get_main_keyboard(True))
    else:
        try:
            await call.message.delete()
        except Exception:
            pass
        await call.message.answer("❌ Amaliyot bekor qilindi.", reply_markup=get_main_keyboard(False))

# ==================== FSM HOLATINI TOZALOVCHI ASOSIY MENYU TUGMALARI ====================
MAIN_MENU_ACTIONS = {
    "🎬 Filmlar", "📺 Seriallar", "🇰🇷 Dramalar", "🍥 Anime",
    "🔍 Film qidirish", "🔢 Kod orqali topish",
    "🔥 Mashhur filmlar", "🆕 Yangi qo‘shilganlar", "🆕 Yangi qo'shilganlar",
    "❤️ Sevimlilar", "📚 Mening tarixim",
    "💡 Film so‘rash", "💡 Film so'rash", "💡 Film buyurtma qilish",
    "⭐ Premium", "👤 Profil", "⚙️ Sozlamalar",
    "💎 Premium sozlamalari", "⚙️ Admin panel"
}

@router.message(F.text.in_(MAIN_MENU_ACTIONS))
async def handle_main_menu_with_state_reset(message: Message, state: FSMContext):
    """
    Agar foydalanuvchi biror FSM holatda (kino nomi, yili, kodi kiritishda) bo'lsa-yu,
    bosh menyu tugmalaridan birini bossa, holat to'liq tozalanadi va tegishli menyu darhol ochiladi!
    """
    cur_state = await state.get_state()
    if cur_state is not None:
        await state.clear()
        try:
            from handlers.media_mgmt import cancel_batch_session
            cancel_batch_session(message.from_user.id)
        except Exception:
            pass

    text = message.text

    if text == "⚙️ Admin panel":
        from handlers.admin import cmd_admin
        await cmd_admin(message)
    elif text == "👤 Profil":
        from handlers.extra import cmd_profile
        await cmd_profile(message)
    elif text == "⚙️ Sozlamalar":
        from handlers.extra import cmd_settings
        await cmd_settings(message)
    elif text == "⭐ Premium":
        from handlers.premium import cmd_premium
        await cmd_premium(message)
    elif text == "💎 Premium sozlamalari":
        from handlers.premium import show_admin_premium_settings
        await show_admin_premium_settings(message, state)
    elif text == "🔍 Film qidirish":
        from handlers.movies import start_search_query
        await start_search_query(message, state)
    elif text == "🔢 Kod orqali topish":
        from handlers.movies import start_code_search
        await start_code_search(message, state)
    elif text == "🎬 Filmlar":
        from handlers.movies import _show_category_page
        await _show_category_page(message, "kino", 1)
    elif text == "📺 Seriallar":
        from handlers.movies import _show_category_page
        await _show_category_page(message, "serial", 1)
    elif text == "🇰🇷 Dramalar":
        from handlers.movies import _show_category_page
        await _show_category_page(message, "drama", 1)
    elif text == "🍥 Anime":
        from handlers.movies import _show_category_page
        await _show_category_page(message, "anime", 1)
    elif text == "🔥 Mashhur filmlar":
        from handlers.movies import show_popular_movies
        await show_popular_movies(message)
    elif text in ("🆕 Yangi qo‘shilganlar", "🆕 Yangi qo'shilganlar"):
        from handlers.movies import show_recent_movies
        await show_recent_movies(message)
    elif text == "❤️ Sevimlilar":
        from handlers.movies import show_favorites
        await show_favorites(message)
    elif text == "📚 Mening tarixim":
        from handlers.movies import show_history
        await show_history(message)
    elif text in ("💡 Film so‘rash", "💡 Film so'rash", "💡 Film buyurtma qilish"):
        from handlers.requests import start_movie_request
        await start_movie_request(message, state)

@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject):
    """
    /start buyrug'i.
    Agar /start <kod> ko'rinishida bo'lsa (Deep linking), to'g'ridan-to'g'ri kinoni ko'rsatadi!
    """
    user_id = message.from_user.id
    is_admin = await db.is_admin(user_id)
    
    # Referal yoki Media kodi mavjudligini tekshirish
    args = command.args
    referrer_id = None
    media_code_to_show = None
    if args:
        clean_args = args.strip()
        if clean_args.startswith("ref_"):
            try:
                referrer_id = int(clean_args.replace("ref_", ""))
            except ValueError:
                pass
        else:
            media_code_to_show = clean_args

    # Foydalanuvchini har doim (deep-link yoki to'g'ridan-to'g'ri tashrif bo'lsa ham) bazada qayd qilish
    await db.add_or_update_user(
        user_id=user_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        referrer_id=referrer_id
    )

    # Agar start bilan birga media kodi yuborilgan bo'lsa (masalan: t.me/bot?start=105)
    if media_code_to_show:
        media = await db.get_media_by_code(media_code_to_show)
        if media:
            await render_media_card(message, media, user_id)
            return

    # Oddiy /start
    import html
    escaped_name = html.escape(message.from_user.full_name or "Foydalanuvchi")
    welcome_text = (
        f"👋 Assalomu alaykum, <b>{escaped_name}</b>!\n\n"
        f"🎬 <b>CineVerse</b> — Filmlar, Seriallar, Anime va Koreys/Xitoy dramalari olamiga xush kelibsiz!\n\n"
        f"🔍 O'zingiz qidirayotgan kinoni topish uchun <b>kodini yuboring</b> yoki quyidagi tugmalardan foydalaning."
    )
    
    await message.answer(welcome_text, parse_mode="HTML", reply_markup=get_main_keyboard(is_admin))
    await message.answer("👇 Quyidagi toifalardan birini tanlang:", reply_markup=get_category_keyboard())

@router.message(Command("menu"))
async def cmd_menu(message: Message):
    is_admin = await db.is_admin(message.from_user.id)
    await message.answer("📋 <b>Asosiy Menyu:</b>", parse_mode="HTML", reply_markup=get_main_keyboard(is_admin))
    await message.answer("👇 Toifalardan birini tanlang:", reply_markup=get_category_keyboard())

@router.message(Command("help"))
@router.message(F.text == "ℹ️ Yordam")
async def cmd_help(message: Message):
    """/help buyrug'i va yordam matni"""
    is_admin = await db.is_admin(message.from_user.id)
    
    help_text = (
        "📖 <b>Botdan foydalanish bo'yicha qo'llanma:</b>\n\n"
        "1️⃣ <b>Kino yoki serial topish:</b>\n"
        "— Botga kino kodini yozib yuboring (Masalan: <code>101</code>).\n"
        "— Yoki «🎬 Kino va seriallar» bo'limidan toifani tanlang.\n"
        "— Yoki «🔍 Qidiruv» orqali nomini yozib qidiring.\n\n"
        "2️⃣ <b>Premium obuna:</b>\n"
        "— Premium orqali barcha eksklyuziv premyeralar, to'liq anime va seriallarni yuqori tezlikda tomosha qilishingiz mumkin.\n"
        "— «⭐ Premium» tugmasi orqali obuna bo'lishingiz mumkin.\n\n"
        "📌 <b>Asosiy buyruqlar:</b>\n"
        "/start — Botni qayta ishga tushirish\n"
        "/movies — Kino va seriallar katalogi\n"
        "/premium — Premium obunani tekshirish yoki xarid qilish\n"
        "/help — Yordam ma'lumotlari\n"
    )

    if is_admin:
        help_text += (
            "\n⚙️ <b>Admin buyruqlari:</b>\n"
            "/admin — Admin paneli\n"
            "/addmedia — Yangi media qo‘shish\n"
            "/deletemedia — Media o‘chirish\n"
            "/medialist — Medialar ro‘yxati\n"
            "/access — Bepul/Pullik sozlash\n"
            "/users — Foydalanuvchilar ro‘yxati\n"
            "/stats — Umumiy statistika\n"
            "/monthly — Oylik faol foydalanuvchilar\n"
            "/blockuser — Foydalanuvchini bloklash\n"
            "/unblockuser — Blokdan chiqarish\n"
            "/addadmin — Yangi admin tayinlash\n"
            "/removeadmin — Adminni olib tashlash\n"
        )

    await message.answer(help_text, parse_mode="HTML")
