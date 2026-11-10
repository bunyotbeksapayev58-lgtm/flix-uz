from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.filters import Command
from database import db
from keyboards import get_premium_plans_keyboard
from config import PREMIUM_PRICES

router = Router()

@router.message(Command("premium"))
@router.message(F.text == "⭐ Premium")
@router.callback_query(F.data == "action:get_premium")
async def show_premium_info(event: Message | CallbackQuery):
    """Premium obuna ma'lumotlari va narxlari"""
    user_id = event.from_user.id
    user_is_prem = await db.is_user_premium(user_id)
    user_data = await db.get_user(user_id)

    status_str = "✅ <b>Faol</b>" if user_is_prem else "❌ <b>Mavjud emas</b>"
    exp_str = f"\n⏳ <i>Tugash muddati:</i> {user_data.get('premium_until', 'Cheksiz')}" if user_is_prem else ""

    text = (
        "💎 <b>FlixUz Cinema Premium Obunasi</b>\n\n"
        "Premium foydalanuvchilar quyidagi barcha imkoniyatlarga ega bo‘ladilar:\n"
        "✨ <b>Barcha eksklyuziv</b> filmlar, seriallar, anime va dramalarni ko‘rish\n"
        "⚡️ <b>Maksimal tezlikda</b> videolarni yuklab olish\n"
        "🚫 <b>Hech qanday reklama</b> va majburiy homiy kanallarsiz foydalanish\n"
        "🎬 <b>Yangi premyeralar</b> eng birinchi navbatda Premiumga joylanadi\n\n"
        f"📊 Sizning holatingiz: {status_str}{exp_str}\n\n"
        "⭐ <b>Telegram Stars orqali avtomatik to‘lash:</b>\n"
        "• 1 oylik — <b>75 Stars</b>\n"
        "• 3 oylik — <b>199 Stars</b>\n"
        "• 1 yillik VIP — <b>599 Stars</b>\n\n"
        "💳 <b>Karta orqali (Click / Payme):</b>\n"
        f"🔹 1 oylik obuna — <b>{PREMIUM_PRICES['1_month']}</b>\n"
        f"🔹 3 oylik obuna — <b>{PREMIUM_PRICES['3_months']}</b>\n"
        f"🔹 1 yillik obuna — <b>{PREMIUM_PRICES['1_year']}</b>\n\n"
        "👇 Quyidagi tugmalardan birini tanlang:"
    )

    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=get_premium_plans_keyboard())
    else:
        await event.message.answer(text, parse_mode="HTML", reply_markup=get_premium_plans_keyboard())
        await event.answer()

@router.callback_query(F.data.startswith("buy_stars:"))
async def send_stars_invoice(call: CallbackQuery):
    """Telegram Stars orqali to'lov invoysini yuborish"""
    plan = call.data.split(":")[1]
    plans = {
        "1_month": {
            "title": "FlixUz 1 Oylik Premium",
            "stars": 75,
            "desc": "1 oy davomida barcha premyera filmlar, serial va animelar cheklovlarsiz!"
        },
        "3_months": {
            "title": "FlixUz 3 Oylik Premium",
            "stars": 199,
            "desc": "3 oy davomida barcha premyera filmlar, serial va animelar cheklovlarsiz!"
        },
        "1_year": {
            "title": "FlixUz 1 Yillik VIP Premium",
            "stars": 599,
            "desc": "1 yil davomida barcha filmlar, seriallar va eng yangi qismlar cheklovlarsiz!"
        },
    }
    info = plans.get(plan)
    if not info:
        await call.answer("Tarif topilmadi!", show_alert=True)
        return

    prices = [LabeledPrice(label=info["title"], amount=info["stars"])]

    await call.message.answer_invoice(
        title=info["title"],
        description=info["desc"],
        payload=f"stars_plan_{plan}",
        currency="XTR",
        prices=prices,
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

    # Bazada Premium faollashtirish
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
