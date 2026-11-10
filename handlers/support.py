import html
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database import db
from keyboards import get_cancel_keyboard, get_main_keyboard

router = Router()

class SupportState(StatesGroup):
    subject = State()
    message = State()
    operator_reply = State()

@router.message(Command("support"))
@router.message(F.text == "💬 Yordam / Murojaat")
async def cmd_support(message: Message, state: FSMContext):
    """Murojaat yaratishni boshlash"""
    await state.set_state(SupportState.subject)
    await message.answer(
        "💬 <b>FlixUz Yordam Markazi</b>\n\n"
        "Murojaatingiz mavzusi yoki qisqacha sababini yozing (masalan: <i>To'lov bo'yicha</i>, <i>Kino topilmadi</i>):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )

@router.message(SupportState.subject)
async def process_ticket_subject(message: Message, state: FSMContext):
    await state.update_data(subject=message.text.strip())
    await state.set_state(SupportState.message)
    await message.answer(
        "📝 Endi muammoingiz yoki savolingizni batafsil yozib yuboring:",
        reply_markup=get_cancel_keyboard()
    )

@router.message(SupportState.message)
async def process_ticket_message(message: Message, state: FSMContext):
    data = await state.get_data()
    subject = data["subject"]
    text = message.text.strip()
    await state.clear()

    ticket = await db.create_support_ticket(message.from_user.id, subject, text)
    is_admin = await db.is_admin(message.from_user.id)

    safe_subject = html.escape(subject)
    safe_text = html.escape(text)
    safe_sender = html.escape(message.from_user.full_name or "Foydalanuvchi")

    await message.answer(
        f"✅ <b>Murojaatingiz qabul qilindi!</b>\n\n"
        f"🎫 Murojaat raqami: <code>#{ticket['ticket_number']}</code>\n"
        f"📌 Mavzu: <b>{safe_subject}</b>\n\n"
        f"Operatorlarimiz tez orada siz bilan bog'lanishadi.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(is_admin)
    )

    # Admin va operatorlarga bildirishnoma yuborish
    admins = await db.get_all_admins()
    alert_text = (
        f"📩 <b>Yangi Support Murojaati!</b>\n\n"
        f"🎫 <b>#{ticket['ticket_number']}</b>\n"
        f"👤 Kimdan: <b>{safe_sender}</b> (<code>{message.from_user.id}</code>)\n"
        f"📌 Mavzu: <b>{safe_subject}</b>\n\n"
        f"💬 Xabar:\n<i>{safe_text}</i>"
    )
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✉️ Javob berish", callback_data=f"reply_ticket:{ticket['id']}:{message.from_user.id}")
    ]])

    for a in admins:
        try:
            await message.bot.send_message(a, alert_text, parse_mode="HTML", reply_markup=markup)
        except Exception:
            pass

@router.callback_query(F.data.startswith("reply_ticket:"))
async def cb_start_ticket_reply(call: CallbackQuery, state: FSMContext):
    """Operator / Admin murojaatga javob yozishi"""
    if not await db.is_admin(call.from_user.id):
        await call.answer("⛔️ Ruxsat berilmagan! Faqat adminlar javob yoza oladi.", show_alert=True)
        return

    _, ticket_id, user_id = call.data.split(":")
    await state.set_state(SupportState.operator_reply)
    await state.update_data(ticket_id=int(ticket_id), target_user_id=int(user_id))
    
    await call.message.answer(
        f"✍️ <code>{user_id}</code> foydalanuvchining <code>#{ticket_id}</code> murojaatiga javobingizni yozing:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await call.answer()

@router.message(SupportState.operator_reply)
async def process_operator_reply(message: Message, state: FSMContext):
    if not await db.is_admin(message.from_user.id):
        await message.answer("⛔️ Ruxsat berilmagan!")
        await state.clear()
        return

    data = await state.get_data()
    ticket_id = data["ticket_id"]
    target_user_id = data["target_user_id"]
    reply_text = (message.text or "").strip()
    if not reply_text:
        await message.answer("Iltimos, matnli javob yozing:")
        return

    await state.clear()

    await db.add_ticket_message(ticket_id, message.from_user.id, reply_text, is_from_admin=True)

    # Foydalanuvchiga yuborish
    try:
        safe_reply = html.escape(reply_text)
        await message.bot.send_message(
            target_user_id,
            f"📩 <b>Operator javobi:</b>\n\n<i>{safe_reply}</i>\n\n"
            f"Agar qo'shimcha savollaringiz bo'lsa, yana /support orqali murojaat qilishingiz mumkin.",
            parse_mode="HTML"
        )
        await message.answer("✅ Javobingiz foydalanuvchiga muvaffaqiyatli yetkazildi!")
    except Exception as e:
        await message.answer(f"❌ Xabarni yetkazishda xatolik: {e}")
