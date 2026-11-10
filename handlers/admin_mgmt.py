import html
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from database import db
from keyboards import get_cancel_keyboard, get_main_keyboard
from utils.states import AddAdminState, RemoveAdminState

router = Router()

async def admin_check(user_id: int) -> bool:
    return await db.is_admin(user_id)

@router.message(Command("addadmin"))
@router.callback_query(F.data == "admin:addadmin")
async def start_add_admin(event: Message | CallbackQuery, state: FSMContext):
    user_id = event.from_user.id
    if not await admin_check(user_id):
        text_warn = "⛔️ Faqat Administratorlar yangi admin qo‘sha oladi!"
        if isinstance(event, Message):
            await event.answer(text_warn)
        else:
            await event.answer(text_warn, show_alert=True)
        return

    await state.set_state(AddAdminState.user_id)

    # Oxirgi foydalanuvchilarni tezkor tanlash uchun olish
    recent_users = await db.get_users_list(limit=5, offset=0)
    admins = await db.get_all_admins()
    
    keyboard_buttons = []
    for u in recent_users:
        if u["id"] not in admins:
            name = u["first_name"] or "Foydalanuvchi"
            un = f" (@{u['username']})" if u.get("username") else ""
            keyboard_buttons.append([
                InlineKeyboardButton(
                    text=f"👤 {name}{un}",
                    callback_data=f"quick_admin:{u['id']}"
                )
            ])
    
    keyboard_buttons.append([
        InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_action")
    ])
    quick_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    text = (
        "👑 <b>Yangi Teng Huquqli Admin Tayinlash:</b>\n\n"
        "Quyidagi usullardan birini tanlang:\n"
        "1️⃣ Tayinlanadigan shaxsning <b>Telegram ID raqamini</b> yuboring\n"
        "2️⃣ Uning yozgan biror xabarini bu yerga <b>Forward (Uzatish)</b> qiling\n"
        "3️⃣ Uning <b>@username</b> nomini yozing (masalan: <code>@foydalanuvchi</code>)\n\n"
        "<i>Yoki quyidagi oxirgi faol foydalanuvchilardan birini tanlang:</i>"
    )

    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=quick_markup)
    else:
        await event.message.answer(text, parse_mode="HTML", reply_markup=quick_markup)
        await event.answer()

@router.callback_query(F.data.startswith("quick_admin:"))
async def cb_quick_add_admin(call: CallbackQuery, state: FSMContext):
    """Tugma orqali foydalanuvchini to'g'ridan-to'g'ri admin qilish"""
    if not await admin_check(call.from_user.id):
        return

    target_id = int(call.data.split(":")[1])
    await state.clear()
    await appoint_admin(call.message, target_id, call.from_user.id)
    await call.answer()

@router.message(AddAdminState.user_id)
async def process_add_admin(message: Message, state: FSMContext):
    if not await admin_check(message.from_user.id):
        return

    target_id = None
    target_name = "Admin"

    # 1. Forward qilingan xabar orqali
    if message.forward_from:
        target_id = message.forward_from.id
        target_name = message.forward_from.full_name
    elif message.forward_sender_name:
        await message.answer("⚠️ Ushbu foydalanuvchi xabarlar uzatishda maxfiylikni yoqib qo'ygan. Iltimos, uning ID raqamini yoki @username nomini yozing:")
        return
    else:
        text = message.text.strip()
        # 2. Raqamli ID orqali
        if text.isdigit():
            target_id = int(text)
            user_info = await db.get_user(target_id)
            if user_info:
                target_name = user_info["first_name"] or str(target_id)
        # 3. @username orqali
        else:
            clean_un = text.lstrip("@").strip()
            found = await db.get_user_by_username(clean_un)
            if found:
                target_id = found["id"]
                target_name = found["first_name"] or f"@{clean_un}"
            else:
                await message.answer(
                    f"❌ «<b>@{clean_un}</b>» bot bazasidan topilmadi!\n"
                    "U kamida bir marta ushbu botga kirib /start bosgan bo'lishi kerak. Qayta kiriting yoki ID yuboring:",
                    parse_mode="HTML"
                )
                return

    await state.clear()
    await appoint_admin(message, target_id, message.from_user.id, target_name)

async def appoint_admin(message: Message, target_id: int, added_by: int, target_name: str = "Admin"):
    """Admin tayinlash va barcha huquqlarni berish"""
    ok = await db.add_admin(user_id=target_id, added_by=added_by)
    safe_name = html.escape(target_name)
    if ok:
        await message.answer(
            f"🎉 <b>Tabriklaymiz!</b>\n"
            f"👤 <b>{safe_name}</b> (<code>{target_id}</code>) muvaffaqiyatli <b>Teng Huquqli Admin</b> etib tayinlandi!\n\n"
            f"Endi u ham:\n"
            f"• Botga yangi kino, serial, anime va dramalar qo‘sha oladi\n"
            f"• Admin Mini Appga to‘liq kirish imkoniyatiga ega bo‘ldi\n"
            f"• Barcha foydalanuvchilar va statistikalarni boshqara oladi\n"
            f"• Barcha filmlarni bepul tomosha qila oladi",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(True)
        )
        
        # Yangi tayinlangan adminga tabrik va yo'riqnoma yuborish
        try:
            bot_info = await message.bot.get_me()
            welcome_admin_text = (
                f"👑 <b>Assalomu alaykum!</b>\n\n"
                f"Sizga @{bot_info.username} botida <b>Teng Huquqli Boshqaruvchi (Admin)</b> maqomi berildi!\n\n"
                f"Siz endi botni to‘liq boshqarishingiz, filmlar yuklashingiz va <b>Admin Mini App</b>dan foydalanishingiz mumkin.\n\n"
                f"👇 Boshqaruvni boshlash uchun quyidagi tugmani bosing yoki /admin yozing:"
            )
            await message.bot.send_message(
                target_id,
                welcome_admin_text,
                parse_mode="HTML",
                reply_markup=get_main_keyboard(True)
            )
        except Exception:
            pass
    else:
        await message.answer(f"⚠️ Ushbu foydalanuvchi (<code>{target_id}</code>) allaqachon admin hisoblanadi.", parse_mode="HTML", reply_markup=get_main_keyboard(True))

# ==================== ADMINNI O'CHIRISH (/removeadmin) ====================

@router.message(Command("removeadmin"))
@router.callback_query(F.data == "admin:removeadmin")
async def start_remove_admin(event: Message | CallbackQuery, state: FSMContext):
    user_id = event.from_user.id
    if not await admin_check(user_id):
        return

    admins = await db.get_all_admins()
    super_admin_id = await db.get_super_admin_id()
    admin_list_text = "📋 <b>Mavjud adminlar ro‘yxati:</b>\n"
    
    keyboard = []
    for a in admins:
        user_info = await db.get_user(a)
        name = user_info["first_name"] if user_info else str(a)
        role = " (Bosh Asoschi)" if a == super_admin_id else ""
        safe_name = html.escape(name)
        admin_list_text += f"— <b>{safe_name}</b> (<code>{a}</code>){role}\n"
        
        # O'chirish uchun tugma (bosh asoschidan tashqari)
        if a != super_admin_id and a != user_id:
            keyboard.append([
                InlineKeyboardButton(text=f"❌ {name} ({a}) ni o‘chirish", callback_data=f"del_admin:{a}")
            ])

    keyboard.append([InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="cancel_action")])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await state.set_state(RemoveAdminState.user_id)
    text = f"{admin_list_text}\nO‘chirmoqchi bo‘lgan adminning ID raqamini kiriting yoki quyidagi tugmani bosing:"
    
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=markup)
    else:
        await event.message.answer(text, parse_mode="HTML", reply_markup=markup)
        await event.answer()

@router.callback_query(F.data.startswith("del_admin:"))
async def cb_delete_admin(call: CallbackQuery, state: FSMContext):
    if not await db.is_admin(call.from_user.id):
        await call.answer("⛔️ Ruxsat berilmagan! Faqat adminlar bajara oladi.", show_alert=True)
        return

    target_id = int(call.data.split(":")[1])
    await state.clear()
    ok = await db.remove_admin(target_id)
    if ok:
        await call.message.edit_text(f"✅ <code>{target_id}</code> adminlikdan olib tashlandi!", parse_mode="HTML")
        try:
            await call.bot.send_message(target_id, "ℹ️ Sizning @FlixUzCinemaBot botidagi adminlik huquqingiz to‘xtatildi.", reply_markup=get_main_keyboard(False))
        except Exception:
            pass
    else:
        await call.answer("O'chirishda xatolik!", show_alert=True)

@router.message(RemoveAdminState.user_id)
async def process_remove_admin_id(message: Message, state: FSMContext):
    if not await db.is_admin(message.from_user.id):
        await message.answer("⛔️ Ruxsat berilmagan!")
        await state.clear()
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Iltimos, ID raqam yoki username yuboring:")
        return

    target_id = None

    if text.isdigit():
        target_id = int(text)
    else:
        clean_un = text.lstrip("@").strip()
        found = await db.get_user_by_username(clean_un)
        if found:
            target_id = found["id"]
        else:
            await message.answer("❌ Bunday foydalanuvchi topilmadi.")
            return

    super_admin_id = await db.get_super_admin_id()
    if target_id == super_admin_id:
        await message.answer("⚠️ Bosh asoschi adminni o‘chirib bo‘lmaydi!", reply_markup=get_main_keyboard(True))
        await state.clear()
        return

    await state.clear()
    ok = await db.remove_admin(target_id)
    if ok:
        await message.answer(f"✅ <code>{target_id}</code> adminlikdan olib tashlandi!", parse_mode="HTML", reply_markup=get_main_keyboard(True))
    else:
        await message.answer(f"❌ <code>{target_id}</code> adminlar ro‘yxatida topilmadi.", reply_markup=get_main_keyboard(True))
