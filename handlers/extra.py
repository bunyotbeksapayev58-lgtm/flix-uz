import html
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import db
from locales.i18n import get_text
from keyboards import get_main_keyboard, get_cancel_keyboard

router = Router()

class PromoState(StatesGroup):
    code = State()

@router.message(Command("profile"))
@router.message(F.text == "👤 Profil")
async def cmd_profile(message: Message):
    user = await db.get_user(message.from_user.id)
    if not user:
        user = await db.add_or_update_user(
            user_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name
        )

    lang = user.get("language", "uz")
    bot_info = await message.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user['id']}"
    status = "⭐ Premium" if user.get("is_premium") else "🆓 Bepul"
    prem_until = user.get("premium_until") or "Mavjud emas"

    text = get_text(
        "profile", lang,
        user_id=user["id"],
        name=html.escape(user["first_name"] or "Foydalanuvchi"),
        username=html.escape(user["username"] or "yo'q"),
        status=status,
        premium_until=prem_until,
        ref_count=user.get("referral_count", 0),
        points=user.get("points", 0),
        ref_link=ref_link
    )

    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟 Promokodni kiritish", callback_data="redeem_promo")],
        [InlineKeyboardButton(text="🌐 Tilni o'zgartirish", callback_data="change_language")]
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

@router.message(Command("language"))
@router.callback_query(F.data == "change_language")
async def cmd_language(event: Message | CallbackQuery):
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇿 O'zbekcha", callback_data="set_lang:uz")],
        [InlineKeyboardButton(text="🇷🇺 Русский", callback_data="set_lang:ru")],
        [InlineKeyboardButton(text="🇬🇧 English", callback_data="set_lang:en")]
    ])
    text = "🌐 <b>Tilni tanlang / Выберите язык / Select language:</b>"
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=markup)
    else:
        await event.message.answer(text, parse_mode="HTML", reply_markup=markup)
        await event.answer()

@router.callback_query(F.data.startswith("set_lang:"))
async def cb_set_language(call: CallbackQuery):
    lang = call.data.split(":")[1]
    await db.set_user_language(call.from_user.id, lang)
    is_admin = await db.is_admin(call.from_user.id)
    msg = get_text("lang_changed", lang)
    await call.message.edit_text(msg, parse_mode="HTML")
    await call.message.answer("Menyu yangilandi:", reply_markup=get_main_keyboard(is_admin))
    await call.answer()

@router.message(Command("settings"))
@router.message(F.text == "⚙️ Sozlamalar")
async def cmd_settings(message: Message):
    user = await db.get_user(message.from_user.id)
    lang = user.get("language", "uz") if user else "uz"
    text = f"⚙️ <b>Sozlamalar:</b>\n\nJoriy til: <b>{lang.upper()}</b>"
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Tilni o'zgartirish", callback_data="change_language")],
        [InlineKeyboardButton(text="🎟 Promokod faollashtirish", callback_data="redeem_promo")]
    ])
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

@router.message(Command("about"))
async def cmd_about(message: Message):
    user = await db.get_user(message.from_user.id)
    lang = user.get("language", "uz") if user else "uz"
    await message.answer(get_text("about", lang), parse_mode="HTML")

@router.message(Command("privacy"))
async def cmd_privacy(message: Message):
    user = await db.get_user(message.from_user.id)
    lang = user.get("language", "uz") if user else "uz"
    await message.answer(get_text("privacy", lang), parse_mode="HTML")

@router.message(Command("terms"))
async def cmd_terms(message: Message):
    user = await db.get_user(message.from_user.id)
    lang = user.get("language", "uz") if user else "uz"
    await message.answer(get_text("terms", lang), parse_mode="HTML")

# ==================== PROMO CODES ====================

@router.message(Command("promo"))
@router.callback_query(F.data == "redeem_promo")
async def start_promo(event: Message | CallbackQuery, state: FSMContext):
    await state.set_state(PromoState.code)
    text = "🎟 <b>Promokod kiriting:</b>\n<i>(Masalan: START2026)</i>"
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    else:
        await event.message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
        await event.answer()

@router.message(PromoState.code)
async def process_promo_code(message: Message, state: FSMContext):
    code_text = message.text.strip()
    await state.clear()
    is_admin = await db.is_admin(message.from_user.id)

    res = await db.redeem_promo_code(message.from_user.id, code_text)
    if res["ok"]:
        await message.answer(f"🎉 {res['message']}", reply_markup=get_main_keyboard(is_admin))
    else:
        await message.answer(f"❌ {res['message']}", reply_markup=get_main_keyboard(is_admin))
