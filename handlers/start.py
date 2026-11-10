from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, CommandObject, Command
from aiogram.fsm.context import FSMContext
from database import db
from keyboards import get_main_keyboard, get_category_keyboard, get_media_view_keyboard
from handlers.movies import render_media_card

router = Router()

@router.message(F.text == "❌ Bekor qilish")
async def cancel_handler(message: Message, state: FSMContext):
    """Har qanday jarayonni bekor qilish"""
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
    is_admin = await db.is_admin(message.from_user.id)
    await message.answer("❌ Jarayon bekor qilindi.", reply_markup=get_main_keyboard(is_admin))

@router.callback_query(F.data == "cancel_action")
async def cancel_callback(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()
    await call.message.answer("❌ Amaliyot bekor qilindi.")
    await call.answer()

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
