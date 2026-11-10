import html
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from database import db
from keyboards import get_cancel_keyboard, get_main_keyboard
from utils.states import MovieRequestState

router = Router()

async def admin_check(user_id: int) -> bool:
    return await db.is_admin(user_id)

# ==================== FOYDALANUVCHI: KINO BUYURTMA QILISH ====================

@router.message(Command("requestmovie"))
@router.message(F.text == "💡 Film so‘rash")
@router.message(F.text == "💡 Film buyurtma qilish")
async def start_movie_request(message: Message, state: FSMContext):
    """Foydalanuvchi kino buyurtma qilishi"""
    await state.set_state(MovieRequestState.title)
    text = (
        "💡 <b>Film buyurtma qilish bo‘limi</b>\n\n"
        "O‘zingiz qidirgan kino, serial yoki animeni topa olmadingizmi?\n"
        "Uning <b>nomini</b> (va imkon bo‘lsa chiqqan yilini) yozib qoldiring:\n\n"
        "<i>(Masalan: Avatar 2, Qasoskorlar: Intiho, yoki Naruto 2-mavsum)</i>"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())

@router.message(MovieRequestState.title)
async def process_movie_request_title(message: Message, state: FSMContext):
    title = message.text.strip()
    await state.clear()
    is_admin = await db.is_admin(message.from_user.id)

    res = await db.create_movie_request(message.from_user.id, title)
    
    await message.answer(
        f"✅ <b>Buyurtmangiz qabul qilindi!</b>\n\n"
        f"🎬 <b>Film nomi:</b> {title}\n"
        f"🆔 So‘rov raqami: <code>#{res['id']}</code>\n\n"
        "Adminlarimiz tez orada ushbu filmni topib botga yuklaydilar. Film yuklangach, sizga avtomatik xabarnoma yuboriladi! 🍿",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(is_admin)
    )

# ==================== ADMIN: KINO SO'ROVLARINI KO'RISH (/requests) ====================

@router.message(Command("requests"))
@router.callback_query(F.data == "admin:requests")
async def show_movie_requests(event: Message | CallbackQuery):
    """Adminlar uchun tushgan kino so'rovlari ro'yxati"""
    user_id = event.from_user.id
    if not await admin_check(user_id):
        return

    requests = await db.get_movie_requests(status="pending", limit=15)
    if not requests:
        text = "📭 Hozircha kutilayotgan kino so‘rovlari mavjud emas."
        if isinstance(event, Message):
            await event.answer(text)
        else:
            await event.message.answer(text)
            await event.answer()
        return

    text = f"💡 <b>Foydalanuvchilardan tushgan buyurtmalar:</b> ({len(requests)} ta)\n\n"
    buttons = []
    for r in requests:
        user_name = html.escape(r.get("first_name") or f"ID: {r['user_id']}")
        movie_title = html.escape(r['movie_title'])
        text += f"🔹 <b>#{r['id']}</b>: «<b>{movie_title}</b>» (Yuboruvchi: {user_name})\n"
        buttons.append([
            InlineKeyboardButton(text=f"✅ #{r['id']} Yuklandi deb belgilash", callback_data=f"req_done:{r['id']}")
        ])

    buttons.append([InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="cancel_action")])
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=markup)
    else:
        await event.message.answer(text, parse_mode="HTML", reply_markup=markup)
        await event.answer()

@router.callback_query(F.data.startswith("req_done:"))
async def cb_fulfill_request(call: CallbackQuery):
    """Buyurtma bajarilganini belgilash va foydalanuvchiga xabar berish"""
    if not await admin_check(call.from_user.id):
        return

    req_id = int(call.data.split(":")[1])
    req = await db.fulfill_movie_request(req_id)
    if not req:
        await call.answer("So'rov topilmadi!", show_alert=True)
        return

    await call.answer("✅ Buyurtma bajarildi deb belgilandi!", show_alert=True)
    await call.message.edit_text(f"✅ <b>#{req_id}</b> raqamli so‘rov («{req['movie_title']}») bajarildi!", parse_mode="HTML")

    # Foydalanuvchiga xushxabar yuborish
    try:
        user_msg = (
            f"🎉 <b>Xushxabar! Siz so‘ragan film botga yuklandi!</b>\n\n"
            f"🎬 <b>Film nomi:</b> «{req['movie_title']}»\n\n"
            f"Uni tomosha qilish uchun botdan qidiring yoki /movies bo‘limidan topishingiz mumkin. Maroqli hordiq tilaymiz! 🍿"
        )
        await call.bot.send_message(req["user_id"], user_msg, parse_mode="HTML")
    except Exception:
        pass
