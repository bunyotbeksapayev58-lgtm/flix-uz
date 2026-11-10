import html
import urllib.parse
from datetime import datetime, timezone
from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    LabeledPrice,
    PreCheckoutQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from database import db
from keyboards import get_premium_plans_keyboard, get_cancel_keyboard, get_main_keyboard
from utils.states import PremiumSettingsState

router = Router()

async def admin_check(user_id: int) -> bool:
    return await db.is_admin(user_id)

async def _get_pricing_settings():
    return {
        "1m_uzs": await db.get_setting("premium_price_1m_uzs", "15 000"),
        "3m_uzs": await db.get_setting("premium_price_3m_uzs", "40 000"),
        "1y_uzs": await db.get_setting("premium_price_1y_uzs", "120 000"),
        "1m_stars": await db.get_setting("premium_price_1m_stars", "75"),
        "3m_stars": await db.get_setting("premium_price_3m_stars", "199"),
        "1y_stars": await db.get_setting("premium_price_1y_stars", "599"),
        "admin_user": (await db.get_setting("payment_admin_username", "admin")).lstrip("@"),
        "admin_id": await db.get_setting("payment_admin_id", "0"),
        "card_num": await db.get_setting("payment_card_number", "8600 0000 0000 0000"),
        "card_holder": await db.get_setting("payment_card_holder", "FlixUz Cinema"),
    }

# ==================== FOYDALANUVCHI UCHUN PREMIUM MENYUSI ====================

@router.message(Command("premium"))
@router.message(F.text == "⭐ Premium")
@router.callback_query(F.data == "action:get_premium")
async def show_premium_info(event: Message | CallbackQuery):
    """Premium obuna ma'lumotlari va narxlari"""
    user_id = event.from_user.id
    user_is_prem = await db.is_user_premium(user_id)
    user_data = await db.get_user(user_id)
    prices = await _get_pricing_settings()

    status_str = "✅ <b>Faol</b>" if user_is_prem else "❌ <b>Mavjud emas</b>"
    exp_str = f"\n⏳ <i>Tugash muddati:</i> {user_data.get('premium_until', 'Cheksiz')}" if user_is_prem else ""

    text = (
        "💎 <b>FlixUz Cinema Premium Obunasi</b>\n\n"
        "Premium foydalanuvchilar quyidagi barcha imkoniyatlarga ega bo‘ladilar:\n"
        "✨ <b>Barcha eksklyuziv</b> filmlar, seriallar, anime va dramalarni to‘liq ko‘rish\n"
        "⚡️ <b>Maksimal tezlikda</b> videolarni yuklab olish\n"
        "🚫 <b>Reklamasiz</b> va majburiy homiy kanallarsiz foydalanish\n"
        "🎬 <b>Yangi premyeralar</b> birinchi navbatda Premiumga joylanadi\n\n"
        f"📊 Sizning holatingiz: {status_str}{exp_str}\n\n"
        "💰 <b>Mavjud tariflar:</b>\n"
        f"• 1 oylik: <b>{prices['1m_uzs']} so'm</b> / <b>{prices['1m_stars']} Stars</b>\n"
        f"• 3 oylik: <b>{prices['3m_uzs']} so'm</b> / <b>{prices['3m_stars']} Stars</b>\n"
        f"• 1 yillik VIP: <b>{prices['1y_uzs']} so'm</b> / <b>{prices['1y_stars']} Stars</b>\n\n"
        "👇 O‘zingizga ma'qul tarifni tanlang:"
    )

    markup = get_premium_plans_keyboard(
        p_1m_uzs=prices["1m_uzs"],
        p_3m_uzs=prices["3m_uzs"],
        p_1y_uzs=prices["1y_uzs"],
        p_1m_stars=prices["1m_stars"],
        p_3m_stars=prices["3m_stars"],
        p_1y_stars=prices["1y_stars"],
    )

    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=markup)
    else:
        await event.message.answer(text, parse_mode="HTML", reply_markup=markup)
        await event.answer()

@router.callback_query(F.data.startswith("plan_choice:"))
async def cb_plan_choice(call: CallbackQuery):
    """Tanlangan tarif bo'yicha to'lov usulini tanlash (Telegram Stars yoki Click/Payme)"""
    plan = call.data.split(":")[1]
    prices = await _get_pricing_settings()

    plans_info = {
        "1_month": {
            "title": "1 Oylik Premium",
            "uzs": prices["1m_uzs"],
            "stars": prices["1m_stars"],
            "desc": "1 oy davomida barcha filmlar, serial va animelar cheklovlarsiz!",
            "days": 30
        },
        "3_months": {
            "title": "3 Oylik Premium",
            "uzs": prices["3m_uzs"],
            "stars": prices["3m_stars"],
            "desc": "3 oy davomida barcha premyeralar va eksklyuziv seriallar!",
            "days": 90
        },
        "1_year": {
            "title": "1 Yillik VIP Premium",
            "uzs": prices["1y_uzs"],
            "stars": prices["1y_stars"],
            "desc": "Butun 1 yil davomida barcha imkoniyatlar to‘liq ochiq!",
            "days": 365
        }
    }

    info = plans_info.get(plan)
    if not info:
        await call.answer("Tarif topilmadi!", show_alert=True)
        return

    text = (
        f"💎 <b>{info['title']}</b>\n\n"
        f"📝 <i>{info['desc']}</i>\n\n"
        f"💵 <b>To‘lov narxi:</b>\n"
        f"💳 Karta orqali: <b>{info['uzs']} so'm</b>\n"
        f"⭐ Telegram Stars orqali: <b>{info['stars']} Stars</b>\n\n"
        f"👇 To‘lovni qaysi usulda amalga oshirmoqchisiz?"
    )

    buttons = [
        [InlineKeyboardButton(text=f"⭐️ Telegram Stars orqali ({info['stars']} ⭐)", callback_data=f"buy_stars:{plan}")],
        [InlineKeyboardButton(text=f"💳 Click / Payme orqali ({info['uzs']} so'm)", callback_data=f"buy_click_payme:{plan}")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="action:get_premium")]
    ]
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()

# ==================== CLICK / PAYME TO'LOVI VA ADMINGA YO'NALTIRISH ====================

@router.callback_query(F.data.startswith("buy_click_payme:"))
async def cb_buy_click_payme(call: CallbackQuery):
    """Click / Payme tanlanganda to'lov rekvizitlarini chiqarish va adminga o'tkazish"""
    plan = call.data.split(":")[1]
    prices = await _get_pricing_settings()
    user_id = call.from_user.id
    user_full_name = html.escape(call.from_user.full_name or "Foydalanuvchi")
    username_str = f"@{call.from_user.username}" if call.from_user.username else f"ID: {user_id}"

    plan_names = {
        "1_month": ("1 Oylik Premium", prices["1m_uzs"], 30),
        "3_months": ("3 Oylik Premium", prices["3m_uzs"], 90),
        "1_year": ("1 Yillik VIP Premium", prices["1y_uzs"], 365)
    }
    p_info = plan_names.get(plan, ("Premium Obuna", "15 000", 30))
    plan_title, plan_uzs, plan_days = p_info

    admin_un = prices["admin_user"]
    card_number = prices["card_num"]
    card_holder = prices["card_holder"]

    prefilled_text = urllib.parse.quote(f"Salom, men {plan_title} uchun to'lov qildim. Mening Telegram ID: {user_id}")
    admin_direct_link = f"https://t.me/{admin_un}?text={prefilled_text}"

    text = (
        "💳 <b>Click / Payme orqali to‘lov:</b>\n\n"
        f"📦 <b>Tanlangan tarif:</b> {plan_title}\n"
        f"💰 <b>To‘lov summasi:</b> <b>{plan_uzs} so'm</b>\n\n"
        f"💳 <b>Karta raqami:</b> <code>{card_number}</code>\n"
        f"👤 <b>Karta egasi:</b> <b>{card_holder}</b>\n\n"
        "📌 <b>Qanday to‘lanadi?</b>\n"
        f"1. Click, Payme yoki bank ilovasi orqali yuqoridagi kartaga <b>{plan_uzs} so'm</b> o‘tkazing.\n"
        "2. To‘lov chekini (skrinshotini) saqlab oling.\n"
        "3. Quyidagi <b>«💬 Adminga yozish va Chek yuborish»</b> tugmasini bosing va chekni yuboring.\n"
        "4. Admin chekni tekshirib, darhol hisobingizga Premium obunani faollashtirib beradi!\n\n"
        f"🆔 Sizning Telegram ID: <code>{user_id}</code>"
    )

    buttons = [
        [InlineKeyboardButton(text="💬 Adminga yozish va Chek yuborish", url=admin_direct_link)],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"plan_choice:{plan}")]
    ]
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await call.answer()

    # Mas'ul adminga to'lov so'rovi va 1-bosishda Premium berish tugmasini jo'natish
    admin_notify_text = (
        "🔔 <b>Yangi Click / Payme to‘lov so‘rovi!</b>\n\n"
        f"👤 <b>Foydalanuvchi:</b> {user_full_name} ({username_str})\n"
        f"🆔 <b>Telegram ID:</b> <code>{user_id}</code>\n"
        f"📦 <b>Tanlangan tarif:</b> {plan_title} ({plan_uzs} so'm)\n\n"
        "<i>Foydalanuvchi sizga chek (skrinshot) yuborishi kutilmoqda.\n"
        "Chekni ko‘rgach, quyidagi tugma orqali darhol 1 bosishda Premium berishingiz mumkin:</i>"
    )
    admin_grant_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ {plan_days} kun Premium yoqish", callback_data=f"quick_grant:{user_id}:{plan_days}")]
    ])

    # Agar belgilangan to'lov admini ID si bo'lsa unga yuboramiz
    target_admin_id = int(prices.get("admin_id") or 0)
    sent_to_admin = False
    if target_admin_id > 0:
        try:
            await call.bot.send_message(target_admin_id, admin_notify_text, parse_mode="HTML", reply_markup=admin_grant_kb)
            sent_to_admin = True
        except Exception:
            pass

    if not sent_to_admin:
        # Barcha adminlarga bildirishnoma jo'natish
        admins = await db.get_admin_ids()
        for aid in admins:
            try:
                await call.bot.send_message(aid, admin_notify_text, parse_mode="HTML", reply_markup=admin_grant_kb)
            except Exception:
                pass

# ==================== ADMINDAN 1-BOSISHDA PREMIUM YOQISH ====================

@router.callback_query(F.data.startswith("quick_grant:"))
async def cb_quick_grant(call: CallbackQuery):
    """Admin to'lov chekini tekshirib, bitta tugma bilan Premium faollashtiradi"""
    if not await admin_check(call.from_user.id):
        await call.answer("⛔️ Ruxsat berilmagan!", show_alert=True)
        return

    parts = call.data.split(":")
    target_user_id = int(parts[1])
    days = int(parts[2])

    await db.set_user_premium(target_user_id, days=days)
    await db.record_payment(
        user_id=target_user_id,
        amount=f"{days}_kun",
        currency="UZS",
        provider="Click/Payme",
        status="completed"
    )

    admin_name = html.escape(call.from_user.first_name or "Admin")
    now_str = datetime.now(timezone.utc).strftime("%H:%M")

    # Foydalanuvchiga xabar jo'natish
    try:
        await call.bot.send_message(
            target_user_id,
            "🎉 <b>Tabriklaymiz, to‘lovingiz muvaffaqiyatli tasdiqlandi!</b>\n\n"
            f"💎 Sizga <b>{days} kunlik Premium obuna</b> faollashtirildi!\n"
            "🍿 <i>Endi barcha eksklyuziv filmlar, seriallar va eng yangi qismlarni cheklovlarsiz tomosha qilishingiz mumkin!</i>\n\n"
            "FlixUz jamoasi maroqli hordiq tilaydi!",
            parse_mode="HTML"
        )
    except Exception:
        pass

    # Admin xabarini yangilash
    await call.message.edit_text(
        call.message.text + f"\n\n✅ <b>Tasdiqlandi!</b> ({admin_name} tomonidan {now_str} da {days} kun Premium yoqildi)",
        parse_mode="HTML"
    )
    await call.answer(f"✅ Foydalanuvchiga {days} kunlik Premium muvaffaqiyatli yoqildi!", show_alert=True)

# ==================== TELEGRAM STARS TO'LOVI ====================

@router.callback_query(F.data.startswith("buy_stars:"))
async def send_stars_invoice(call: CallbackQuery):
    """Telegram Stars orqali to'lov invoysini yuborish"""
    plan = call.data.split(":")[1]
    prices = await _get_pricing_settings()

    plans = {
        "1_month": {
            "title": "FlixUz 1 Oylik Premium",
            "stars": int(prices["1m_stars"]),
            "desc": "1 oy davomida barcha filmlar, serial va animelar to‘liq cheklovlarsiz!"
        },
        "3_months": {
            "title": "FlixUz 3 Oylik Premium",
            "stars": int(prices["3m_stars"]),
            "desc": "3 oy davomida barcha premyeralar va yangi qismlar!"
        },
        "1_year": {
            "title": "FlixUz 1 Yillik VIP Premium",
            "stars": int(prices["1y_stars"]),
            "desc": "1 yil davomida barcha filmlar va VIP imkoniyatlar!"
        },
    }
    info = plans.get(plan)
    if not info:
        await call.answer("Tarif topilmadi!", show_alert=True)
        return

    price_items = [LabeledPrice(label=info["title"], amount=info["stars"])]

    await call.message.answer_invoice(
        title=info["title"],
        description=info["desc"],
        payload=f"stars_plan_{plan}",
        currency="XTR",
        prices=price_items,
        provider_token=""  # Telegram Stars uchun bo'sh bo'ladi
    )
    await call.answer()

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    """Telegram to'lovidan oldin tasdiqlash"""
    await pre_checkout_query.answer(ok=True)

@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    """Muvaffaqiyatli to'lovdan keyin avtomatik Premium yoqish"""
    payload = message.successful_payment.invoice_payload
    plan_map = {
        "stars_plan_1_month": 30,
        "stars_plan_3_months": 90,
        "stars_plan_1_year": 365
    }
    days = plan_map.get(payload, 30)
    user_id = message.from_user.id
    stars_amount = message.successful_payment.total_amount
    charge_id = message.successful_payment.telegram_payment_charge_id

    # Idempotentlik tekshiruvi: takroriy to'lov qayd qilinmaydi
    if await db.is_transaction_processed(charge_id):
        return

    await db.set_user_premium(user_id, days=days)
    await db.record_payment(
        user_id=user_id,
        amount=str(stars_amount),
        currency="XTR",
        provider="Telegram Stars",
        status="completed",
        transaction_id=charge_id
    )

    await message.answer(
        f"🎉 <b>Tabriklaymiz, to‘lov muvaffaqiyatli qabul qilindi!</b>\n\n"
        f"💎 Sizga <b>{days} kunlik Premium obuna</b> avtomatik faollashtirildi!\n"
        f"⭐ To‘langan summa: <b>{stars_amount} Telegram Stars</b>\n"
        f"🧾 To‘lov ID: <code>{charge_id}</code>\n\n"
        f"🍿 <i>Endi barcha filmlar va qismlarni cheklovlarsiz tomosha qilishingiz mumkin!</i>",
        parse_mode="HTML"
    )

@router.callback_query(F.data == "check_premium_status")
async def cb_check_premium_status(call: CallbackQuery):
    user_is_prem = await db.is_user_premium(call.from_user.id)
    user_data = await db.get_user(call.from_user.id)
    
    if user_is_prem:
        exp = user_data.get('premium_until') or 'Cheksiz'
        await call.answer(f"✅ Sizda Premium faol!\nTugash vaqti: {exp}", show_alert=True)
    else:
        await call.answer("❌ Sizda hozircha Premium obuna yo'q.", show_alert=True)

# ==================== ADMIN UCHUN PREMIUM SOZLAMALARI MENYUSI ====================

@router.message(Command("premium_settings"))
@router.message(F.text == "💎 Premium sozlamalari")
@router.callback_query(F.data == "admin:premium_settings")
async def show_admin_premium_settings(event: Message | CallbackQuery, state: FSMContext):
    """Admin uchun Premium narxlari, to'lov admini va karta sozlamalari"""
    user_id = event.from_user.id
    if not await admin_check(user_id):
        if isinstance(event, CallbackQuery):
            await event.answer("⛔️ Siz admin emassiz!", show_alert=True)
        return

    await state.clear()
    prices = await _get_pricing_settings()

    text = (
        "⚙️ <b>FlixUz Premium va To‘lov Sozlamalari</b>\n\n"
        "💰 <b>So‘mdagi narxlar (Click / Payme):</b>\n"
        f"• 1 oylik: <b>{prices['1m_uzs']} so'm</b>\n"
        f"• 3 oylik: <b>{prices['3m_uzs']} so'm</b>\n"
        f"• 1 yillik VIP: <b>{prices['1y_uzs']} so'm</b>\n\n"
        "⭐ <b>Telegram Stars narxlari:</b>\n"
        f"• 1 oylik: <b>{prices['1m_stars']} Stars</b>\n"
        f"• 3 oylik: <b>{prices['3m_stars']} Stars</b>\n"
        f"• 1 yillik VIP: <b>{prices['1y_stars']} Stars</b>\n\n"
        "👤 <b>To‘lov qabul qiluvchi admin (Pin qilingan):</b>\n"
        f"• <b>@{prices['admin_user']}</b> (ID: <code>{prices['admin_id']}</code>)\n\n"
        "💳 <b>Karta rekvizitlari:</b>\n"
        f"• Karta: <code>{prices['card_num']}</code>\n"
        f"• Egasi: <b>{prices['card_holder']}</b>\n\n"
        "<i>Quyidagi tugmalar orqali sozlamalarni o‘zgartirishingiz mumkin:</i>"
    )

    buttons = [
        [InlineKeyboardButton(text="💰 So'm narxlarini o'zgartirish", callback_data="pset:uzs")],
        [InlineKeyboardButton(text="⭐ Stars narxlarini o'zgartirish", callback_data="pset:stars")],
        [InlineKeyboardButton(text="📌 To'lov adminini tanlash (Pin qilish)", callback_data="pset:admin")],
        [InlineKeyboardButton(text="💳 Karta rekvizitlarini o'zgartirish", callback_data="pset:card")],
        [InlineKeyboardButton(text="🔙 Admin panelga qaytish", callback_data="pset:back")]
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=markup)
    else:
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        await event.answer()

@router.callback_query(F.data == "pset:back")
async def cb_pset_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("⚙️ Admin panel bosh menyusi:", reply_markup=get_main_keyboard(True))
    await call.answer()

# --- 1. SO'MDAGI NARXLARNI SOZLASH ---
@router.callback_query(F.data == "pset:uzs")
async def start_edit_uzs(call: CallbackQuery, state: FSMContext):
    if not await admin_check(call.from_user.id):
        return
    await state.set_state(PremiumSettingsState.edit_uzs_1m)
    await call.message.answer(
        "💰 <b>1 oylik Premium narxini kiriting (so'mda):</b>\n<i>(Masalan: <code>15 000</code>)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await call.answer()

@router.message(PremiumSettingsState.edit_uzs_1m)
async def process_uzs_1m(message: Message, state: FSMContext):
    val = message.text.strip()
    await state.update_data(uzs_1m=val)
    await state.set_state(PremiumSettingsState.edit_uzs_3m)
    await message.answer(
        "💰 <b>3 oylik Premium narxini kiriting (so'mda):</b>\n<i>(Masalan: <code>40 000</code>)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )

@router.message(PremiumSettingsState.edit_uzs_3m)
async def process_uzs_3m(message: Message, state: FSMContext):
    val = message.text.strip()
    await state.update_data(uzs_3m=val)
    await state.set_state(PremiumSettingsState.edit_uzs_1y)
    await message.answer(
        "💰 <b>1 yillik VIP Premium narxini kiriting (so'mda):</b>\n<i>(Masalan: <code>120 000</code>)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )

@router.message(PremiumSettingsState.edit_uzs_1y)
async def process_uzs_1y(message: Message, state: FSMContext):
    val = message.text.strip()
    data = await state.get_data()
    await state.clear()

    await db.set_setting("premium_price_1m_uzs", data["uzs_1m"])
    await db.set_setting("premium_price_3m_uzs", data["uzs_3m"])
    await db.set_setting("premium_price_1y_uzs", val)

    await message.answer(
        "✅ <b>So‘mdagi narxlar muvaffaqiyatli saqlandi!</b>\n\n"
        f"• 1 oylik: <b>{data['uzs_1m']} so'm</b>\n"
        f"• 3 oylik: <b>{data['uzs_3m']} so'm</b>\n"
        f"• 1 yillik: <b>{val} so'm</b>",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(True)
    )

# --- 2. STARS NARXLARINI SOZLASH ---
@router.callback_query(F.data == "pset:stars")
async def start_edit_stars(call: CallbackQuery, state: FSMContext):
    if not await admin_check(call.from_user.id):
        return
    await state.set_state(PremiumSettingsState.edit_stars_1m)
    await call.message.answer(
        "⭐ <b>1 oylik Premium narxini Stars'da kiriting:</b>\n<i>(Faqat butun son, masalan: <code>75</code>)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await call.answer()

@router.message(PremiumSettingsState.edit_stars_1m)
async def process_stars_1m(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit():
        await message.answer("❌ Faqat raqam kiriting (masalan: 75):")
        return
    await state.update_data(stars_1m=val)
    await state.set_state(PremiumSettingsState.edit_stars_3m)
    await message.answer(
        "⭐ <b>3 oylik Premium narxini Stars'da kiriting:</b>\n<i>(Masalan: <code>199</code>)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )

@router.message(PremiumSettingsState.edit_stars_3m)
async def process_stars_3m(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit():
        await message.answer("❌ Faqat raqam kiriting (masalan: 199):")
        return
    await state.update_data(stars_3m=val)
    await state.set_state(PremiumSettingsState.edit_stars_1y)
    await message.answer(
        "⭐ <b>1 yillik VIP Premium narxini Stars'da kiriting:</b>\n<i>(Masalan: <code>599</code>)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )

@router.message(PremiumSettingsState.edit_stars_1y)
async def process_stars_1y(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit():
        await message.answer("❌ Faqat raqam kiriting (masalan: 599):")
        return
    data = await state.get_data()
    await state.clear()

    await db.set_setting("premium_price_1m_stars", data["stars_1m"])
    await db.set_setting("premium_price_3m_stars", data["stars_3m"])
    await db.set_setting("premium_price_1y_stars", val)

    await message.answer(
        "✅ <b>Telegram Stars narxlari muvaffaqiyatli saqlandi!</b>\n\n"
        f"• 1 oylik: <b>{data['stars_1m']} Stars</b>\n"
        f"• 3 oylik: <b>{data['stars_3m']} Stars</b>\n"
        f"• 1 yillik: <b>{val} Stars</b>",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(True)
    )

# --- 3. TO'LOV ADMININI TANLASH (PIN QILISH) ---
@router.callback_query(F.data == "pset:admin")
async def start_edit_admin(call: CallbackQuery, state: FSMContext):
    if not await admin_check(call.from_user.id):
        return
    await state.set_state(PremiumSettingsState.edit_payment_admin)
    buttons = [
        [InlineKeyboardButton(text="🙋‍♂️ Meni to‘lov admini qilib pin qilish", callback_data="pset:pin_me")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_action")]
    ]
    await call.message.answer(
        "👤 <b>To‘lov qabul qiluvchi adminni sozlash:</b>\n\n"
        "Foydalanuvchilar Click / Payme to‘lovini amalga oshirgach, chekni qaysi adminga yuborishini belgilang:\n\n"
        "• Adminning <b>@username</b> nomini yuboring\n"
        "• Yoki uning xabarini <b>Forward</b> qilib tashlang\n"
        "• Yoki o‘zingizni tayinlash uchun quyidagi tugmani bosing:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await call.answer()

@router.callback_query(F.data == "pset:pin_me")
async def cb_pin_current_admin(call: CallbackQuery, state: FSMContext):
    """Joriy adminni to'lov admini sifatida pin qilish"""
    user = call.from_user
    username = user.username or f"user_{user.id}"
    await db.set_setting("payment_admin_username", username)
    await db.set_setting("payment_admin_id", str(user.id))
    await state.clear()

    await call.message.answer(
        f"✅ <b>Siz to‘lov qabul qiluvchi admin sifatida muvaffaqiyatli pin qilindingiz!</b>\n\n"
        f"👤 Admin: @{username}\n"
        f"🆔 ID: <code>{user.id}</code>\n\n"
        "Endi Click va Payme orqali to‘lov qiluvchilar to‘g‘ridan-to‘g‘ri sizning profilingizga o‘tadi.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(True)
    )
    await call.answer()

@router.message(PremiumSettingsState.edit_payment_admin)
async def process_payment_admin_input(message: Message, state: FSMContext):
    target_un = ""
    target_id = 0

    if message.forward_from:
        target_un = message.forward_from.username or ""
        target_id = message.forward_from.id
    elif message.text:
        text = message.text.strip()
        if text.isdigit():
            target_id = int(text)
            u = await db.get_user(target_id)
            if u and u.get("username"):
                target_un = u["username"]
        else:
            target_un = text.lstrip("@").strip()
            u = await db.get_user_by_username(target_un)
            if u:
                target_id = u["id"]

    if not target_un and not target_id:
        await message.answer("❌ Admin topilmadi. @username yoki Telegram ID sini qayta yuboring:")
        return

    if not target_un:
        target_un = f"id_{target_id}"

    await db.set_setting("payment_admin_username", target_un)
    await db.set_setting("payment_admin_id", str(target_id))
    await state.clear()

    await message.answer(
        f"✅ <b>To‘lov qabul qiluvchi admin yangilandi!</b>\n\n"
        f"👤 Admin: @{target_un}\n"
        f"🆔 ID: <code>{target_id}</code>\n\n"
        "Foydalanuvchilar to‘lov qilganda aynan shu adminga yo‘naltiriladi.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(True)
    )

# --- 4. KARTA REKVIZITLARINI SOZLASH ---
@router.callback_query(F.data == "pset:card")
async def start_edit_card(call: CallbackQuery, state: FSMContext):
    if not await admin_check(call.from_user.id):
        return
    await state.set_state(PremiumSettingsState.edit_card_details)
    await call.message.answer(
        "💳 <b>Click / Payme karta rekvizitlarini kiriting:</b>\n\n"
        "Format: <code>Karta raqami, Karta egasining ismi</code>\n"
        "<i>(Masalan: <code>8600 1234 5678 9010, Ali Valiyev</code>)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await call.answer()

@router.message(PremiumSettingsState.edit_card_details)
async def process_card_details(message: Message, state: FSMContext):
    text = message.text.strip()
    if "," in text:
        parts = text.split(",", 1)
        card_num = parts[0].strip()
        card_holder = parts[1].strip()
    else:
        card_num = text
        card_holder = "FlixUz Cinema"

    await db.set_setting("payment_card_number", card_num)
    await db.set_setting("payment_card_holder", card_holder)
    await state.clear()

    await message.answer(
        "✅ <b>Karta rekvizitlari muvaffaqiyatli saqlandi!</b>\n\n"
        f"💳 Karta: <code>{card_num}</code>\n"
        f"👤 Egasi: <b>{card_holder}</b>",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(True)
    )
