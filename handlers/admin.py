import html
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from config import SUPER_ADMIN_IDS
from database import db
from keyboards import get_admin_keyboard, get_cancel_keyboard, get_main_keyboard
from utils.states import BlockUserState, UnblockUserState, GrantPremiumState

router = Router()

async def admin_check(user_id: int) -> bool:
    return await db.is_admin(user_id)

@router.message(Command("admin"))
@router.message(F.text == "⚙️ Admin panel")
async def cmd_admin(message: Message):
    """Admin boshqaruv panelini ochish"""
    user_id = message.from_user.id
    if not await admin_check(user_id):
        admins = await db.get_all_admins()
        # Agar tizimda hali hech qanday admin bo'lmasa, birinchi foydalanuvchiga super admin bo'lish imkoniyati
        if not admins and not SUPER_ADMIN_IDS:
            markup = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👑 Meni Bosh Admin (Super Admin) qilish", callback_data="admin:claim_super_admin")]
            ])
            await message.answer(
                f"⚠️ <b>Tizimda hali birorta ham administrator belgilanmagan!</b>\n\n"
                f"Siz ushbu botning ilk admini bo'lishingiz mumkin.\n"
                f"🆔 <b>Sizning Telegram ID:</b> <code>{user_id}</code>\n\n"
                f"Quyidagi tugmani bosing:",
                parse_mode="HTML",
                reply_markup=markup
            )
            return

        await message.answer(
            f"⛔️ <b>Kechirasiz, siz admin emassiz!</b>\n\n"
            f"🆔 <b>Sizning Telegram ID raqamingiz:</b> <code>{user_id}</code>\n\n"
            f"💡 <i>Admin boshqaruv huquqini olish uchun ushbu ID raqamni serverdagi <code>.env</code> faylida "
            f"<code>SUPER_ADMIN_ID={user_id}</code> deb ko'rsating yoki mavjud administratorga murojaat qiling.</i>",
            parse_mode="HTML"
        )
        return

    text = (
        "👑 <b>Admin boshqaruv paneli</b>\n\n"
        "Quyidagi boshqaruv bo'limlaridan birini tanlang:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=get_admin_keyboard())

@router.callback_query(F.data == "admin:claim_super_admin")
async def cb_claim_super_admin(call: CallbackQuery):
    admins = await db.get_all_admins()
    if admins:
        await call.answer("❌ Tizimda adminlar allaqachon mavjud!", show_alert=True)
        return

    user_id = call.from_user.id
    await db.add_admin(user_id, role="super_admin", added_by=0)
    await call.answer("🎉 Siz muvaffaqiyatli Super Admin etib tayinlandingiz!", show_alert=True)
    await call.message.edit_text(
        f"👑 <b>Tabriklaymiz! Siz tizimning Bosh Admini (Super Admin) etib tayinlandingiz!</b>\n"
        f"🆔 Telegram ID: <code>{user_id}</code>\n\n"
        f"Quyidagi menyudan boshqaruvni boshlashingiz mumkin:",
        parse_mode="HTML",
        reply_markup=get_admin_keyboard()
    )
    await call.message.answer("Asosiy menyu yangilandi:", reply_markup=get_main_keyboard(True))

@router.callback_query(F.data == "admin:miniapp_info")
async def cb_miniapp_info(call: CallbackQuery):
    text = (
        "📱 <b>Admin Mini App haqida yo'riqnoma:</b>\n\n"
        "Telegram rasmiy xavfsizlik qoidalariga ko'ra, Telegram Web App (Mini App) faqat "
        "<b>HTTPS</b> xavfsiz protokoli orqali ishlaydi (HTTP havolalar Telegram ichida ochilmaydi).\n\n"
        "Mini Appni Telegram ichida ochish uchun:\n"
        "1️⃣ Serveringizga SSL sertifikat o'rnating yoki <code>ngrok / cloudflare tunnel</code> orqali HTTPS havola oling.\n"
        "2️⃣ <code>.env</code> faylida <code>WEBAPP_URL=https://sizning-saytingiz.com</code> ko'rinishida yozing.\n"
        "3️⃣ Botni qayta ishga tushiring.\n\n"
        "💡 <i>Hozircha barcha boshqaruv amallarini (kinolar, qismlar, kanallar, statistika, to'lovlar) "
        "ushbu Admin Paneldagi tugmalar orqali 100% to'liq bajara olasiz!</i>"
    )
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()

# ==================== STATISTIKA (/stats, /monthly) ====================

@router.message(Command("stats"))
@router.callback_query(F.data == "admin:stats")
async def show_stats(event: Message | CallbackQuery):
    """Umumiy statistika"""
    user_id = event.from_user.id
    if not await admin_check(user_id):
        return

    stats = await db.get_overall_stats()
    monthly_users = await db.get_monthly_users_count()

    text = (
        "📊 <b>Umumiy Bot Statistikasi:</b>\n\n"
        f"👥 <b>Jami foydalanuvchilar:</b> {stats['total_users']} ta\n"
        f"⭐ <b>Premium foydalanuvchilar:</b> {stats['premium_users']} ta\n"
        f"📅 <b>Oxirgi 30 kunda faol bo'lganlar:</b> {monthly_users} ta\n"
        f"🚫 <b>Bloklanganlar:</b> {stats['blocked_users']} ta\n\n"
        f"🎬 <b>Jami medialar:</b> {stats['total_media']} ta\n"
        f"  ├ 🎬 Filmlar: {stats['kino_count']} ta\n"
        f"  ├ 📺 Seriallar: {stats['serial_count']} ta\n"
        f"  ├ ⛩ Anime: {stats['anime_count']} ta\n"
        f"  └ 🎭 Dramalar: {stats['drama_count']} ta\n\n"
        f"🆓 <b>Bepul medialar:</b> {stats['free_media']} ta\n"
        f"🔒 <b>Premium medialar:</b> {stats['premium_media']} ta\n"
        f"👁 <b>Jami ko‘rishlar soni:</b> {stats['total_views']} marta"
    )

    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML")
    else:
        await event.message.answer(text, parse_mode="HTML")
        await event.answer()

@router.message(Command("monthly"))
@router.callback_query(F.data == "admin:monthly")
async def show_monthly(event: Message | CallbackQuery):
    """Oylik faol foydalanuvchilar statistikasi"""
    user_id = event.from_user.id
    if not await admin_check(user_id):
        return

    monthly = await db.get_monthly_users_count()
    total = await db.get_total_users_count()
    percentage = (monthly / total * 100) if total > 0 else 0

    text = (
        "📅 <b>Oylik Foydalanuvchilar Ko'rsatkichi:</b>\n\n"
        f"📈 <b>Oxirgi 30 kunda faol / yangi qo'shilganlar:</b> {monthly} nafar\n"
        f"👥 <b>Jami foydalanuvchilarga nisbatan ulushi:</b> {percentage:.1f}%\n"
    )

    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML")
    else:
        await event.message.answer(text, parse_mode="HTML")
        await event.answer()

# ==================== FOYDALANUVCHILARNI RO'YXATGA OLISH (/users) ====================

@router.message(Command("users"))
@router.callback_query(F.data == "admin:users")
async def cmd_users_list(event: Message | CallbackQuery):
    """Foydalanuvchilar ro'yxati va eksport"""
    user_id = event.from_user.id
    if not await admin_check(user_id):
        return

    total = await db.get_total_users_count()
    users = await db.get_users_list(limit=25, offset=0)

    text = f"👥 <b>Foydalanuvchilar soni:</b> {total} ta\n\n<b>Oxirgi qo‘shilganlar:</b>\n"
    for u in users:
        prem = "⭐" if u["is_premium"] else "👤"
        block = " [🚫 Bloklangan]" if u["is_blocked"] else ""
        name = html.escape(u["first_name"] or "NoName")
        username = f"@{html.escape(u['username'])}" if u["username"] else "mavjud emas"
        text += f"{prem} <code>{u['id']}</code> | {name} ({username}){block}\n"

    target_msg = event if isinstance(event, Message) else event.message
    await target_msg.answer(text, parse_mode="HTML")

    # To'liq ro'yxatni fayl sifatida tayyorlash
    all_users = await db.get_users_list(limit=2000, offset=0)
    lines = ["ID,Username,FirstName,IsPremium,IsBlocked,JoinedAt"]
    for u in all_users:
        lines.append(f"{u['id']},{u['username'] or ''},{u['first_name'] or ''},{u['is_premium']},{u['is_blocked']},{u['joined_at']}")
    csv_bytes = "\n".join(lines).encode("utf-8")
    
    file = BufferedInputFile(csv_bytes, filename="users_list.csv")
    await target_msg.answer_document(file, caption="📄 Barcha foydalanuvchilar ro‘yxati (CSV)")
    if isinstance(event, CallbackQuery):
        await event.answer()

# ==================== BLOKLASH VA BLOKDAN CHIQARISH ====================

@router.message(Command("blockuser"))
@router.callback_query(F.data == "admin:blockuser")
async def start_block_user(event: Message | CallbackQuery, state: FSMContext):
    user_id = event.from_user.id
    if not await admin_check(user_id):
        return

    await state.set_state(BlockUserState.user_id)
    text = "🚫 <b>Bloklamoqchi bo'lgan foydalanuvchining Telegram ID raqamini yuboring:</b>"
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    else:
        await event.message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
        await event.answer()

@router.message(BlockUserState.user_id)
async def process_block_user(message: Message, state: FSMContext):
    target_text = (message.text or "").strip()
    if not target_text.isdigit():
        await message.answer("❌ ID faqat raqamlardan iborat bo'lishi kerak! Qayta kiriting:")
        return

    target_id = int(target_text)
    await state.clear()
    
    ok = await db.block_user(target_id)
    if ok:
        await message.answer(f"✅ Foydalanuvchi <code>{target_id}</code> muvaffaqiyatli bloklandi!", parse_mode="HTML", reply_markup=get_main_keyboard(True))
    else:
        await message.answer(f"⚠️ Foydalanuvchi <code>{target_id}</code> bazadan topilmadi.", parse_mode="HTML", reply_markup=get_main_keyboard(True))

@router.message(Command("unblockuser"))
@router.callback_query(F.data == "admin:unblockuser")
async def start_unblock_user(event: Message | CallbackQuery, state: FSMContext):
    user_id = event.from_user.id
    if not await admin_check(user_id):
        return

    await state.set_state(UnblockUserState.user_id)
    text = "✅ <b>Blokdan chiqarmoqchi bo'lgan foydalanuvchining Telegram ID raqamini yuboring:</b>"
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    else:
        await event.message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
        await event.answer()

@router.message(UnblockUserState.user_id)
async def process_unblock_user(message: Message, state: FSMContext):
    target_text = (message.text or "").strip()
    if not target_text.isdigit():
        await message.answer("❌ ID faqat raqamlardan iborat bo'lishi kerak! Qayta kiriting:")
        return

    target_id = int(target_text)
    await state.clear()
    
    ok = await db.unblock_user(target_id)
    if ok:
        await message.answer(f"✅ Foydalanuvchi <code>{target_id}</code> blokdan chiqarildi!", parse_mode="HTML", reply_markup=get_main_keyboard(True))
    else:
        await message.answer(f"⚠️ Foydalanuvchi <code>{target_id}</code> bazadan topilmadi.", parse_mode="HTML", reply_markup=get_main_keyboard(True))

# ==================== PREMIUM BERISH ====================

@router.callback_query(F.data == "admin:grant_premium")
async def start_grant_premium(call: CallbackQuery, state: FSMContext):
    if not await admin_check(call.from_user.id):
        return

    await state.set_state(GrantPremiumState.user_id)
    await call.message.answer(
        "⭐ <b>Premium obuna bermoqchi bo'lgan foydalanuvchining Telegram ID raqamini yuboring:</b>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await call.answer()

@router.message(GrantPremiumState.user_id)
async def process_grant_user_id(message: Message, state: FSMContext):
    target_text = (message.text or "").strip()
    if not target_text.isdigit():
        await message.answer("❌ ID faqat raqamlardan iborat bo'lishi kerak. Qayta kiriting:")
        return

    await state.update_data(target_id=int(target_text))
    await state.set_state(GrantPremiumState.days)
    await message.answer("⏳ Necha kunlik Premium bermoqchisiz? (Masalan: <code>30</code>, <code>90</code>, <code>365</code>):", parse_mode="HTML")

@router.message(GrantPremiumState.days)
async def process_grant_days(message: Message, state: FSMContext):
    days_text = (message.text or "").strip()
    if not days_text.isdigit():
        await message.answer("❌ Kunlar soni faqat raqamlardan iborat bo'lishi kerak:")
        return

    data = await state.get_data()
    target_id = data["target_id"]
    days = int(days_text)
    await state.clear()

    ok = await db.set_user_premium(target_id, days=days)
    if ok:
        await message.answer(
            f"🎉 <code>{target_id}</code> foydalanuvchisiga <b>{days} kunlik Premium</b> muvaffaqiyatli berildi!",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(True)
        )
        try:
            await message.bot.send_message(
                target_id,
                f"🎉 Tabriklaymiz! Sizga administrator tomonidan <b>{days} kunlik Premium obuna</b> faollashtirildi!",
                parse_mode="HTML"
            )
        except Exception:
            pass
    else:
        await message.answer("❌ Xatolik yuz berdi. Foydalanuvchi bazada mavjudligini tekshiring.", reply_markup=get_main_keyboard(True))

# ==================== BAZA ZAXIRASI VA TIKLASH (/backup, /restore) ====================

@router.message(Command("backup"))
@router.callback_query(F.data == "admin:backup")
async def cmd_admin_backup(event: Message | CallbackQuery):
    """Ma'lumotlar bazasining to'liq zaxira nusxasini yaratish va adminga yuborish"""
    user_id = event.from_user.id
    if not await admin_check(user_id):
        return

    from workers.backup_manager import perform_database_backup_file, send_backup_to_telegram, verify_sqlite_database
    from aiogram.types import FSInputFile

    if isinstance(event, CallbackQuery):
        await event.answer("⏳ Zaxira yaratilmoqda...")
        msg_obj = event.message
    else:
        msg_obj = event

    status_msg = await msg_obj.answer("⏳ <i>Ma'lumotlar bazasi zaxiralanmoqda...</i>", parse_mode="HTML")
    backup_file = await perform_database_backup_file()

    if not backup_file or not backup_file.exists():
        await status_msg.edit_text("❌ Zaxira nusxasi yaratishda xatolik yuz berdi.")
        return

    is_valid, info_msg, media_cnt, user_cnt = verify_sqlite_database(backup_file)
    size_kb = round(backup_file.stat().st_size / 1024, 1)

    caption = (
        f"💾 <b>FlixUz Baza Zaxirasi (#CINEMA_DB_BACKUP)</b>\n\n"
        f"📊 <b>Kinolar/Seriallar soni:</b> {media_cnt} ta\n"
        f"👥 <b>Foydalanuvchilar:</b> {user_cnt} ta\n"
        f"📁 <b>Fayl hajmi:</b> {size_kb} KB\n\n"
        f"💡 <i>Ushbu faylni saqlab qo'ying. Kelgusida server yangilansa yoki qayta ishga tushsa, "
        f"ushbu faylni botga yuborib bir soniyada barcha kinolarni tiklashingiz mumkin.</i>"
    )

    doc = FSInputFile(str(backup_file), filename=backup_file.name)
    await msg_obj.answer_document(doc, caption=caption, parse_mode="HTML")
    try:
        await status_msg.delete()
    except Exception:
        pass

@router.message(Command("restore"))
@router.callback_query(F.data == "admin:restore_info")
async def cmd_restore_info(event: Message | CallbackQuery):
    """Baza tiklash bo'yicha yo'riqnoma"""
    user_id = event.from_user.id
    if not await admin_check(user_id):
        return

    text = (
        "📥 <b>Ma'lumotlar bazasini tiklash (Restore) bo‘limi:</b>\n\n"
        "Agar server yangilanib yoki qayta o'chib-yonib kinolar yo'qolgan bo'lsa:\n\n"
        "1️⃣ Avval olingan <code>.db</code> zaxira faylini ushbu botga oddiy hujjat (fayl) sifatida yuboring.\n"
        "2️⃣ Bot fayl butunligini tekshiradi va barcha kinolar hamda foydalanuvchilarni 1 soniyada to'liq tiklaydi!\n\n"
        "💡 <i>Shuningdek, zaxira kanalini ulagan bo'lsangiz (<code>BACKUP_CHANNEL_ID</code>), "
        "bot server yoqilishi bilanoq oxirgi zaxirani o'zi avtomatik yuklab oladi!</i>"
    )

    if isinstance(event, CallbackQuery):
        await event.message.answer(text, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, parse_mode="HTML")

@router.message(F.document & F.document.file_name.endswith(".db"))
async def process_restore_db_document(message: Message):
    """Admin tomonidan yuborilgan .db fayli orqali bazani tiklash"""
    user_id = message.from_user.id
    if not await admin_check(user_id):
        return

    from workers.backup_manager import restore_database_from_file_path, BACKUP_DIR
    from config import DB_PATH
    import tempfile

    doc = message.document
    status_msg = await message.answer("⏳ <i>Fayl yuklab olinmoqda va tekshirilmoqda...</i>", parse_mode="HTML")

    temp_path = BACKUP_DIR / f"temp_upload_{doc.file_unique_id}.db"
    try:
        await message.bot.download(doc.file_id, destination=temp_path)
        ok, res_text = await restore_database_from_file_path(temp_path)
        if ok:
            # Ma'lumotlar bazasi ulanishini qayta yangilash
            await db.init_db()
            await status_msg.edit_text(
                f"🎉 <b>{res_text}</b>\n\nBarcha kinolar, seriallar va foydalanuvchilar muvaffaqiyatli tiklandi!",
                parse_mode="HTML"
            )
            await message.answer("Asosiy menyu:", reply_markup=get_main_keyboard(True))
        else:
            await status_msg.edit_text(f"❌ <b>Baza tiklanmadi:</b>\n{res_text}", parse_mode="HTML")
    except Exception as e:
        await status_msg.edit_text(f"❌ Xatolik yuz berdi: {e}", parse_mode="HTML")
    finally:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass

