import asyncio
import time
import re
import html
from typing import Dict, Any, Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from database import db
from keyboards import (
    get_cancel_keyboard,
    get_main_keyboard,
    get_category_select_keyboard,
    get_media_access_choice_keyboard,
)
from utils.states import (
    AddMediaState,
    AddEpisodeState,
    DeleteMediaState,
    AccessMediaState,
    BatchUploadState,
    EpisodeAccessState,
    ChannelMgmtState,
    ChannelPostState,
)

router = Router()

_batch_locks: Dict[int, asyncio.Lock] = {}
_batch_sessions: Dict[int, Dict[str, Any]] = {}

def get_user_lock(user_id: int) -> asyncio.Lock:
    if user_id not in _batch_locks:
        _batch_locks[user_id] = asyncio.Lock()
    return _batch_locks[user_id]

def extract_episode_num(caption: Optional[str] = None, file_name: Optional[str] = None) -> Optional[int]:
    texts_to_check = []
    if caption:
        texts_to_check.append(str(caption).strip())
    if file_name:
        texts_to_check.append(str(file_name).strip())

    for text in texts_to_check:
        # 1. Patterns like "15-qism", "15 qism", "15_qism", "15 ep", "15 серия", "15 part"
        m = re.search(r'(?i)(?<![a-zA-Z0-9])(\d{1,4})\s*[-_.\s]*(?:qism|q|ep|episode|серия|сер|part)\b', text)
        if m:
            return int(m.group(1))

        # 2. Patterns like "qism 15", "qism: 15", "ep 15", "ep: 15", "episode 15", "серия 15", "q: 15"
        m = re.search(r'(?i)(?<![a-zA-Z0-9])(?:qism|q|ep|episode|серия|сер|part)\s*[:#№\-_\s]?\s*(\d{1,4})(?!\d)', text)
        if m:
            return int(m.group(1))

        # 3. Pattern S01E15, S1E07, E15, EP15
        m = re.search(r'(?i)(?<![a-zA-Z0-9])[sS]\d{1,2}[eE](\d{1,4})(?!\d)', text)
        if m:
            return int(m.group(1))
        m = re.search(r'(?i)(?<![a-zA-Z0-9])(?:ep|e)(\d{1,4})(?!\d)', text)
        if m:
            return int(m.group(1))

        # 4. Filename like "Naruto_15.mp4" or "Series - 15.mkv"
        m = re.search(r'(?i)[_ \-\[](\d{1,4})[\]_ \-\.]', text)
        if m:
            num = int(m.group(1))
            if num not in (360, 480, 720, 1080, 1440, 2160, 1990, 2000, 2010, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027):
                return num

        # 5. Pure number, e.g. "15"
        if text.strip().isdigit():
            return int(text.strip())

    return None

async def _delayed_batch_summary(bot, chat_id: int, user_id: int):
    try:
        await asyncio.sleep(2.5)
    except asyncio.CancelledError:
        return

    session = _batch_sessions.get(user_id)
    if not session or not session.get("status_msg_id"):
        return

    ep_list = sorted(set(session.get("episodes_added", [])))
    if not ep_list:
        return

    min_ep = ep_list[0]
    max_ep = ep_list[-1]
    count = len(ep_list)
    free_up_to = session.get("free_up_to", 0)

    pricing_info = ""
    if free_up_to > 0:
        pricing_info = f"\n🆓 <b>Bepul qismlar:</b> 1 — {free_up_to}-qismlar\n⭐ <b>Pullik qismlar:</b> {free_up_to + 1} va undan keyingilari"
    else:
        pricing_info = "\n🆓 <b>Barcha qismlar:</b> Bepul"

    summary_text = (
        f"✅ <b>Ommaviy yuklash qabul qilindi!</b>\n\n"
        f"🎬 <b>Serial:</b> {session['title']} [<code>{session['media_code']}</code>]\n"
        f"📥 <b>Qo‘shilgan qismlar:</b> {count} ta ({min_ep} dan {max_ep}-qismgacha){pricing_info}\n\n"
        f"💡 <i>Yana boshqa qismlarni yuborishingiz mumkin yoki jarayonni yakunlash uchun quyidagi tugmani bosing:</i>"
    )
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=session["status_msg_id"],
            text=summary_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Yuklashni yakunlash", callback_data="batch_finish")]
            ])
        )
    except Exception:
        pass

async def admin_check(user_id: int) -> bool:
    return await db.is_admin(user_id)

# ==================== MEDIA QO'SHISH (/addmedia) ====================

@router.message(Command("addmedia"))
@router.callback_query(F.data == "admin:addmedia")
async def start_add_media(event: Message | CallbackQuery, state: FSMContext):
    """Media qo'shishni boshlash (Kategoriya tanlash)"""
    user_id = event.from_user.id
    if not await admin_check(user_id):
        return

    await state.clear()
    await state.set_state(AddMediaState.category)
    text = "➕ <b>Yangi media qo‘shish:</b>\n\nQaysi toifaga qo‘shmoqchisiz?"
    
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=get_category_select_keyboard())
    else:
        await event.message.answer(text, parse_mode="HTML", reply_markup=get_category_select_keyboard())
        await event.answer()

@router.callback_query(AddMediaState.category, F.data.startswith("select_cat:"))
async def process_media_category(call: CallbackQuery, state: FSMContext):
    cat = call.data.split(":")[1]
    await state.update_data(category=cat)
    await state.set_state(AddMediaState.title)
    
    await call.message.delete()
    cat_names = {
        "kino": "🎬 Film",
        "serial": "📺 Serial",
        "anime": "🍥 Anime",
        "drama": "🇰🇷 Drama"
    }
    await call.message.answer(
        f"✅ Toifa tanlandi: <b>{cat_names.get(cat, cat.capitalize())}</b>\n\n"
        "Endi media <b>nomini</b> kiriting:\n<i>(Masalan: Avatar 2, Qashqirlar Makoni, Naruto)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await call.answer()

@router.message(AddMediaState.title)
async def process_media_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(AddMediaState.original_title)
    await message.answer(
        "🎬 Medianing <b>asl/inglizcha nomini</b> kiriting (yoki o‘tkazib yuborish uchun «-» deb yozing):\n"
        "<i>(Masalan: Avatar: The Way of Water)</i>",
        parse_mode="HTML"
    )

@router.message(AddMediaState.original_title)
async def process_media_original_title(message: Message, state: FSMContext):
    orig = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(original_title=orig)
    await state.set_state(AddMediaState.poster)
    await message.answer(
        "🖼 Film/Serial uchun <b>poster rasmini (rasm fayli)</b> yuboring:\n"
        "<i>(Agar rasmsiz qo‘shmoqchi bo‘lsangiz, shunchaki «-» deb yozing)</i>",
        parse_mode="HTML"
    )

@router.message(AddMediaState.poster, F.photo)
async def process_media_poster_photo(message: Message, state: FSMContext):
    poster_id = message.photo[-1].file_id
    await state.update_data(poster_file_id=poster_id)
    await state.set_state(AddMediaState.genre)
    await message.answer("🎭 Media <b>janrini</b> kiriting (yoki «-» deb yuboring):\n<i>(Masalan: Fantastika, Jangari, Komediya)</i>", parse_mode="HTML")

@router.message(AddMediaState.poster, F.text)
async def process_media_poster_skip(message: Message, state: FSMContext):
    await state.update_data(poster_file_id="")
    await state.set_state(AddMediaState.genre)
    await message.answer("🎭 Media <b>janrini</b> kiriting (yoki «-» deb yuboring):\n<i>(Masalan: Fantastika, Jangari, Komediya)</i>", parse_mode="HTML")

@router.message(AddMediaState.genre)
async def process_media_genre(message: Message, state: FSMContext):
    genre = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(genre=genre)
    await state.set_state(AddMediaState.year)
    await message.answer("📅 Chiqqan <b>yilini</b> kiriting (masalan: 2024, yoki «-»):", parse_mode="HTML")

@router.message(AddMediaState.year)
async def process_media_year(message: Message, state: FSMContext):
    year = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(year=year)
    await state.set_state(AddMediaState.duration)
    await message.answer("⏱ <b>Davomiyligini</b> kiriting (masalan: <code>120 daqiqa</code>, <code>45 daqiqa</code>, yoki «-»):", parse_mode="HTML")

@router.message(AddMediaState.duration)
async def process_media_duration(message: Message, state: FSMContext):
    dur = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(duration=dur)
    await state.set_state(AddMediaState.language)
    await message.answer("🌐 <b>Tilini / Dublyaj turini</b> kiriting (masalan: <code>O'zbek tilida (Dublyaj)</code>, yoki «-»):", parse_mode="HTML")

@router.message(AddMediaState.language)
async def process_media_language(message: Message, state: FSMContext):
    lang = "O'zbekcha" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(language=lang)
    await state.set_state(AddMediaState.age_rating)
    await message.answer("🔞 <b>Yosh chegarasini</b> kiriting (masalan: <code>16+</code>, <code>18+</code>, <code>12+</code> yoki «-»):", parse_mode="HTML")

@router.message(AddMediaState.age_rating)
async def process_media_age_rating(message: Message, state: FSMContext):
    age = "12+" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(age_rating=age)
    await state.set_state(AddMediaState.description)
    await message.answer("📝 Qisqacha <b>tavsif/syujet</b> yozing (yoki «-»):", parse_mode="HTML")

@router.message(AddMediaState.description)
async def process_media_description(message: Message, state: FSMContext):
    desc = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(description=desc)
    await state.set_state(AddMediaState.code)

    code_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Avtomatik kod yaratish", callback_data="auto_code_gen")]
    ])
    await message.answer(
        "🔑 Media uchun <b>noyob qidiruv kodini</b> kiriting:\n"
        "<i>(Masalan: 12345, 101, AN04)</i>\n\n"
        "Yoki tizim o‘zi tasodifiy kod berishi uchun quyidagi tugmani bosing:",
        parse_mode="HTML",
        reply_markup=code_markup
    )

@router.callback_query(AddMediaState.code, F.data == "auto_code_gen")
async def cb_auto_code_gen(call: CallbackQuery, state: FSMContext):
    new_code = await db.generate_unique_code()
    await state.update_data(code=new_code)
    await state.set_state(AddMediaState.is_premium)
    await call.message.edit_text(f"✅ Avtomatik kod tanlandi: <code>{new_code}</code>", parse_mode="HTML")
    await call.message.answer(
        "🔒 Ushbu media qanday toifaga tegishli bo‘lsin?",
        reply_markup=get_media_access_choice_keyboard()
    )
    await call.answer()

@router.message(AddMediaState.code)
async def process_media_code(message: Message, state: FSMContext):
    code = message.text.strip()
    if code.lower() in ["auto", "avto"]:
        code = await db.generate_unique_code()
    else:
        existing = await db.get_media_by_code(code)
        if existing:
            await message.answer(
                f"⚠️ <code>{code}</code> kodi allaqachon mavjud! Boshqa kod kiriting yoki «auto» deb yozing:",
                parse_mode="HTML"
            )
            return

    await state.update_data(code=code)
    await state.set_state(AddMediaState.is_premium)
    await message.answer(
        f"✅ Kod belgilandi: <code>{code}</code>\n\n🔒 Ushbu media qanday toifaga tegishli bo‘lsin?",
        parse_mode="HTML",
        reply_markup=get_media_access_choice_keyboard()
    )

@router.callback_query(AddMediaState.is_premium, F.data.startswith("access_type:"))
async def process_media_access_type(call: CallbackQuery, state: FSMContext):
    access_val = int(call.data.split(":")[1])
    await state.update_data(is_premium=access_val)
    await state.set_state(AddMediaState.file)
    
    await call.message.delete()
    status_label = "⭐ Faqat Premium" if access_val == 1 else "🆓 Bepul"
    await call.message.answer(
        f"✅ Kirish darajasi: <b>{status_label}</b>\n\n"
        "📹 Endi ushbu medianing <b>video faylini</b> (yoki hujjat shaklidagi videosini) yuboring:\n"
        "<i>(Serial yoki Anime bo'lsa, 1-qism videosini yuboring)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await call.answer()

@router.message(AddMediaState.file, F.video | F.document)
async def process_media_file(message: Message, state: FSMContext):
    """Video yoki hujjat faylni qabul qilish va bazaga yozish"""
    if message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
    else:
        await message.answer("Iltimos, video yoki video-fayl yuboring!")
        return

    data = await state.get_data()
    await state.clear()

    ok = await db.add_media(
        code=data["code"],
        category=data["category"],
        title=data["title"],
        original_title=data.get("original_title", ""),
        poster_file_id=data.get("poster_file_id", ""),
        genre=data.get("genre", ""),
        year=data.get("year", ""),
        duration=data.get("duration", ""),
        language=data.get("language", "O'zbekcha"),
        age_rating=data.get("age_rating", "12+"),
        description=data.get("description", ""),
        file_id=file_id,
        file_type=file_type,
        is_premium=data["is_premium"]
    )

    if ok:
        category = data["category"].lower()
        if category in ["serial", "anime", "drama"]:
            await db.add_episode(
                media_code=data["code"],
                season_num=1,
                episode_num=1,
                title="1-qism",
                file_id=file_id,
                is_premium=0
            )

        access_str = "⭐ Faqat Premium" if data["is_premium"] else "🆓 Bepul"
        bot_info = await message.bot.get_me()
        msg = (
            "🎉 <b>Media muvaffaqiyatli saqlandi!</b>\n\n"
            f"🎬 <b>Nomi:</b> {data['title']}\n"
            f"📂 <b>Toifa:</b> {data['category'].capitalize()}\n"
            f"🔑 <b>Kod:</b> <code>{data['code']}</code>\n"
            f"💎 <b>Kirish:</b> {access_str}\n\n"
            f"🔗 <b>To‘g‘ridan-to‘g‘ri havola:</b>\n"
            f"<code>https://t.me/{bot_info.username}?start={data['code']}</code>"
        )
        if category in ["serial", "anime", "drama"]:
            msg += (
                f"\n\n📺 <b>1-qism saqlandi!</b>\n"
                f"📦 Barcha qismlarni bir vaqtda birdaniga yuklash uchun: <code>/batchupload</code> buyrug‘idan foydalaning!"
            )

        buttons = []
        if category in ["serial", "anime", "drama"]:
            buttons.append([InlineKeyboardButton(text="📦 Qismlarni ommaviy yuklash (Batch)", callback_data=f"batch_start:{data['code']}")])
        post_channel = await db.get_setting("posting_channel")
        if post_channel:
            buttons.append([InlineKeyboardButton(text="🚀 Kanalga post qilish", callback_data=f"chan_post:{data['code']}")])

        inline_post_kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None

        await message.answer(msg, parse_mode="HTML", reply_markup=inline_post_kb or get_main_keyboard(True))
        if inline_post_kb:
            await message.answer("Bosh menyu:", reply_markup=get_main_keyboard(True))
    else:
        await message.answer("❌ Saqlashda xatolik yuz berdi. Kod takrorlanmaganligini tekshiring.", reply_markup=get_main_keyboard(True))

# ==================== OMMAVIY QISMLARNI YUKLASH (/batchupload) ====================

@router.callback_query(F.data.startswith("batch_start:"))
async def cb_quick_batch_start(call: CallbackQuery, state: FSMContext):
    """Serial yoki animeni qo'shgandan so'ng darhol qismlarni ommaviy yuklashga o'tish"""
    user_id = call.from_user.id
    if not await admin_check(user_id):
        await call.answer("⛔️ Ruxsat berilmagan!", show_alert=True)
        return

    code = call.data.split(":")[1]
    media = await db.get_media_by_code(code)
    if not media:
        await call.answer("❌ Media topilmadi!", show_alert=True)
        return

    episodes = await db.get_episodes(code)
    next_ep = len(episodes) + 1

    await state.clear()
    await state.update_data(media_code=code, title=media["title"], current_ep=next_ep)
    await state.set_state(BatchUploadState.start_ep)

    await call.message.answer(
        f"📦 <b>{media['title']}</b> [<code>{code}</code>] uchun ommaviy yuklash:\n\n"
        f"📊 Bazada mavjud qismlar: <b>{len(episodes)} ta</b>\n"
        f"Yuklashni <b>nechanchi qismdan</b> boshlamoqchisiz? (Tavsiya: <code>{next_ep}</code>):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await call.answer()

@router.message(Command("batchupload"))
@router.message(Command("addepisodes"))
@router.callback_query(F.data == "admin:batchupload")
async def start_batch_upload(event: Message | CallbackQuery, state: FSMContext):
    """Ommaviy qismlarni bir vaqtda yuklash rejimi"""
    user_id = event.from_user.id
    if not await admin_check(user_id):
        return

    await state.clear()
    await state.set_state(BatchUploadState.media_code)
    text = (
        "📦 <b>Ommaviy qismlarni yuklash rejimi:</b>\n\n"
        "Qaysi serial, anime yoki dramaning qismlarini yuklamoqchisiz?\n"
        "Uning <b>kodini</b> yuboring (Masalan: <code>12345</code>):"
    )
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    else:
        await event.message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
        await event.answer()

@router.message(BatchUploadState.media_code)
async def process_batch_media_code(message: Message, state: FSMContext):
    code = message.text.strip()
    media = await db.get_media_by_code(code)
    if not media:
        await message.answer(f"❌ <code>{code}</code> kodi bo‘yicha hech qanday serial topilmadi. Qayta kiriting:")
        return

    episodes = await db.get_episodes(code)
    next_ep = len(episodes) + 1
    await state.update_data(media_code=code, title=media["title"], current_ep=next_ep)
    await state.set_state(BatchUploadState.start_ep)

    await message.answer(
        f"🎬 <b>{media['title']}</b> [<code>{code}</code>]\n"
        f"📊 Bazada mavjud qismlar: <b>{len(episodes)} ta</b>\n\n"
        f"Yuklashni <b>nechanchi qismdan</b> boshlamoqchisiz? (Tavsiya: <code>{next_ep}</code>):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )

@router.message(BatchUploadState.start_ep)
async def process_batch_start_ep(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Qism raqami faqat son bo'lishi kerak. Qayta kiriting:")
        return

    start_ep = int(text)
    await state.update_data(current_ep=start_ep, start_ep=start_ep)
    await state.set_state(BatchUploadState.free_up_to)

    threshold_text = (
        "💰 <b>Qismlar uchun to‘lov shartini belgilang:</b>\n\n"
        "Nechanchi qismgacha <b>BEPUL</b> bo‘lsin?\n"
        "<i>Masalan: <code>25</code> deb yozsangiz, 1 dan 25-qismgacha BEPUL, 26-qismdan boshlab ⭐ Premium (pullik) bo‘ladi.</i>\n\n"
        "• Barcha qismlar bepul bo‘lishi uchun: <code>0</code> deb yozing.\n"
        "• Barcha qismlar pullik bo‘lishi uchun: <code>1</code> deb yozing."
    )
    await message.answer(threshold_text, parse_mode="HTML", reply_markup=get_cancel_keyboard())

@router.message(BatchUploadState.free_up_to)
async def process_batch_free_threshold(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Raqam kiriting (masalan: 25 yoki 0):")
        return

    free_up_to = int(text)
    data = await state.get_data()
    media_code = data["media_code"]
    start_ep = data["start_ep"]

    await state.update_data(free_up_to=free_up_to, uploaded_count=0)
    await state.set_state(BatchUploadState.uploading)

    rule_info = f"1-{free_up_to} qismlar bepul, {free_up_to + 1}+ qismlar ⭐ Premium" if free_up_to > 0 else "Barcha qismlar bepul"

    finish_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yuklashni yakunlash", callback_data="batch_finish")]
    ])

    ready_text = (
        "🚀 <b>Ommaviy yuklash rejimi faollashdi!</b>\n\n"
        f"🎬 <b>Serial:</b> {data['title']} [<code>{media_code}</code>]\n"
        f"🔢 <b>Boshlang'ich qism:</b> {start_ep}-qism\n"
        f"💎 <b>To‘lov sharti:</b> {rule_info}\n\n"
        "👉 <b>Istalgancha videolarni (15, 20, 50, 100 ta) birdaniga tanlab yuboring!</b>\n"
        "• Bot barcha videolarni avtomatik ketma-ket qabul qiladi.\n"
        "• Agar fayl nomi yoki izohida qism raqami bo'lsa (masalan: <i>15-qism</i>), avtomatik to'g'ri raqamlanadi.\n"
        "• Yoki File ID lar ro'yxatini matn sifatida tashlashingiz ham mumkin.\n\n"
        "<i>Barcha qismlarni yuborib bo‘lgach, quyidagi «✅ Yuklashni yakunlash» tugmasini bosing:</i>"
    )
    await message.answer(ready_text, parse_mode="HTML", reply_markup=finish_kb)

@router.message(BatchUploadState.uploading, F.video | F.document)
async def process_batch_incoming_file(message: Message, state: FSMContext):
    """Ommaviy rejimda kelgan har bir video yoki hujjatni navbatdagi qism sifatida saqlash (FloodWait va Race Condition himoyasi bilan)"""
    user_id = message.from_user.id
    if not await admin_check(user_id):
        return

    if message.video:
        file_id = message.video.file_id
        file_name = message.video.file_name or ""
        file_type = "video"
    elif message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or ""
        file_type = "document"
    else:
        return

    async with get_user_lock(user_id):
        data = await state.get_data()
        media_code = data.get("media_code")
        if not media_code:
            return

        current_ep = data.get("current_ep", 1)
        free_up_to = data.get("free_up_to", 0)

        caption = message.caption or ""
        detected_ep = extract_episode_num(caption, file_name)

        if detected_ep is not None and detected_ep > 0:
            ep_num = detected_ep
            if ep_num >= current_ep:
                next_ep = ep_num + 1
            else:
                next_ep = current_ep
        else:
            ep_num = current_ep
            next_ep = current_ep + 1

        is_prem = 1 if (free_up_to > 0 and ep_num > free_up_to) else 0

        await db.add_episode(
            media_code=media_code,
            episode_num=ep_num,
            season_num=1,
            title=f"{ep_num}-qism",
            file_id=file_id,
            file_type=file_type,
            is_premium=is_prem
        )

        session = _batch_sessions.setdefault(user_id, {
            "status_msg_id": None,
            "chat_id": message.chat.id,
            "last_edit_time": 0.0,
            "timer_task": None,
            "total_received": 0,
            "episodes_added": [],
            "media_code": media_code,
            "title": data.get("title", media_code),
            "free_up_to": free_up_to
        })

        session["total_received"] += 1
        session["episodes_added"].append(ep_num)

        await state.update_data(current_ep=next_ep, uploaded_count=session["total_received"])

        finish_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Yuklashni yakunlash", callback_data="batch_finish")]
        ])

        prem_badge = "⭐ Premium" if is_prem else "🆓 Bepul"

        if session["status_msg_id"] is None:
            try:
                status_msg = await message.answer(
                    f"⏳ <b>Ommaviy qismlar qabul qilinmoqda...</b>\n\n"
                    f"🎬 <b>Serial:</b> {session['title']} [<code>{media_code}</code>]\n"
                    f"📥 <b>Qabul qilindi:</b> {session['total_received']} ta qism\n"
                    f"⚡️ <b>Oxirgi:</b> {ep_num}-qism ({prem_badge})\n\n"
                    f"<i>Barcha fayllar qabul qilinmoqda, kuting...</i>",
                    parse_mode="HTML",
                    reply_markup=finish_kb
                )
                session["status_msg_id"] = status_msg.message_id
                session["last_edit_time"] = time.monotonic()
            except Exception:
                pass
        else:
            now = time.monotonic()
            if now - session.get("last_edit_time", 0.0) >= 1.5:
                session["last_edit_time"] = now
                try:
                    await message.bot.edit_message_text(
                        chat_id=session["chat_id"],
                        message_id=session["status_msg_id"],
                        text=(
                            f"⏳ <b>Ommaviy qismlar qabul qilinmoqda...</b>\n\n"
                            f"🎬 <b>Serial:</b> {session['title']} [<code>{media_code}</code>]\n"
                            f"📥 <b>Qabul qilindi:</b> {session['total_received']} ta qism\n"
                            f"⚡️ <b>Oxirgi:</b> {ep_num}-qism ({prem_badge})\n\n"
                            f"<i>Fayllar kelmoqda, yana tashlashingiz mumkin...</i>"
                        ),
                        parse_mode="HTML",
                        reply_markup=finish_kb
                    )
                except Exception:
                    pass

        # Trailing timer yangilash (oxirgi fayldan 2.5s o'tgach xulosa xabari chiqariladi)
        if session.get("timer_task") and not session["timer_task"].done():
            session["timer_task"].cancel()

        session["timer_task"] = asyncio.create_task(
            _delayed_batch_summary(message.bot, session["chat_id"], user_id)
        )

@router.message(BatchUploadState.uploading, F.text == "✅ Yuklashni yakunlash")
@router.callback_query(F.data == "batch_finish")
async def finish_batch_upload(event: Message | CallbackQuery, state: FSMContext):
    """Ommaviy yuklashni yakunlash va to'liq hisobot berish"""
    user_id = event.from_user.id
    data = await state.get_data()
    await state.clear()

    # Session tozalash va timer bekor qilish
    session = _batch_sessions.pop(user_id, None)
    if session and session.get("timer_task") and not session["timer_task"].done():
        session["timer_task"].cancel()

    media_code = data.get("media_code") or (session.get("media_code") if session else "")
    title = data.get("title") or (session.get("title") if session else "")
    count = data.get("uploaded_count", 0)
    if session and session.get("total_received", 0) > count:
        count = session["total_received"]
    free_up_to = data.get("free_up_to", 0)
    if session and "free_up_to" in session:
        free_up_to = session["free_up_to"]

    ep_list = session.get("episodes_added", []) if session else []
    if ep_list:
        min_ep = min(ep_list)
        max_ep = max(ep_list)
        range_str = f"({min_ep} dan {max_ep}-qismgacha)"
    else:
        range_str = ""

    summary = (
        "🎉 <b>Ommaviy qismlar yuklash muvaffaqiyatli yakunlandi!</b>\n\n"
        f"🎬 <b>Serial:</b> {title} [<code>{media_code}</code>]\n"
        f"📥 <b>Jami saqlangan qismlar:</b> {count} ta {range_str}\n"
    )
    if free_up_to > 0:
        summary += f"🆓 <b>Bepul qismlar:</b> 1 — {free_up_to}-qismlar\n⭐ <b>Pullik qismlar:</b> {free_up_to + 1} va undan keyingilari\n"
    else:
        summary += "🆓 <b>Barcha qismlar:</b> Bepul\n"

    summary += "\nEndi foydalanuvchilar ushbu qismlarni tomosha qilishlari mumkin! 🍿"

    if isinstance(event, Message):
        await event.answer(summary, parse_mode="HTML", reply_markup=get_main_keyboard(True))
    else:
        await event.message.answer(summary, parse_mode="HTML", reply_markup=get_main_keyboard(True))
        await event.answer("✅ Yakunlandi!")

@router.message(BatchUploadState.uploading, F.text & ~F.text.in_({"✅ Yuklashni yakunlash", "❌ Bekor qilish", "/cancel", "/batchupload"}))
async def process_batch_text_list(message: Message, state: FSMContext):
    """Admin ommaviy File ID lar ro'yxatini matn sifatida tashlaganda qabul qilish"""
    text = (message.text or "").strip()
    if text in ["✅ Yuklashni yakunlash", "❌ Bekor qilish", "Bekor qilish", "/cancel", "/batchupload"]:
        return

    user_id = message.from_user.id
    if not await admin_check(user_id):
        return

    data = await state.get_data()
    media_code = data.get("media_code")
    if not media_code:
        return

    current_ep = data.get("current_ep", 1)
    free_up_to = data.get("free_up_to", 0)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    episodes_to_add = []

    for line in lines:
        m = re.match(r'^(\d+)\s*[:\-–]\s*(.+)$', line)
        if m:
            ep_num = int(m.group(1))
            fid = m.group(2).strip()
            if ep_num >= current_ep:
                current_ep = ep_num + 1
        else:
            ep_num = current_ep
            current_ep += 1
            fid = line.strip()

        if len(fid) < 10:
            continue

        is_prem = 1 if (free_up_to > 0 and ep_num > free_up_to) else 0
        episodes_to_add.append({
            "episode_num": ep_num,
            "title": f"{ep_num}-qism",
            "file_id": fid,
            "file_type": "video",
            "is_premium": is_prem
        })

    if not episodes_to_add:
        await message.answer("❌ Matnda yaroqli File ID lar topilmadi. Har bir qatorda bittadan File ID yuboring yoki video fayllarni tashlang.")
        return

    count = await db.add_episodes_batch(media_code, episodes_to_add)
    await state.update_data(current_ep=current_ep, uploaded_count=data.get("uploaded_count", 0) + count)

    finish_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yuklashni yakunlash", callback_data="batch_finish")]
    ])
    await message.answer(
        f"✅ <b>{count} ta qism</b> matndan o‘qib olindi va bazaga muvaffaqiyatli saqlandi!\n\n"
        f"Yana videolarni yoki File ID larni yuborishingiz mumkin (yoki yakunlang):",
        parse_mode="HTML",
        reply_markup=finish_kb
    )



# ==================== QISMLAR NARXINI SOZLASH (/epaccess) ====================

@router.message(Command("epaccess"))
@router.callback_query(F.data == "admin:epaccess")
async def start_ep_access(event: Message | CallbackQuery, state: FSMContext):
    """Mavjud serialning qaysi qismlari bepul va qaysilari pullikligini sozlash"""
    user_id = event.from_user.id
    if not await admin_check(user_id):
        return

    await state.set_state(EpisodeAccessState.media_code)
    text = "💰 <b>Qismlar narxi (Threshold) sozlash:</b>\n\nQaysi serial/anime qismlarini sozlamoqchisiz? <b>Kodi</b>ni kiriting:"
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    else:
        await event.message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
        await event.answer()

@router.message(EpisodeAccessState.media_code)
async def process_ep_access_code(message: Message, state: FSMContext):
    code = message.text.strip()
    media = await db.get_media_by_code(code)
    if not media:
        await message.answer(f"❌ <code>{code}</code> kodi bo‘yicha serial topilmadi. Qayta kiriting:")
        return

    episodes = await db.get_episodes(code)
    await state.update_data(media_code=code, title=media["title"])
    await state.set_state(EpisodeAccessState.free_up_to)

    await message.answer(
        f"🎬 <b>{media['title']}</b> [<code>{code}</code>]\n"
        f"Jami mavjud qismlar: {len(episodes)} ta.\n\n"
        "Nechanchi qismgacha <b>BEPUL</b> bo‘lsin?\n"
        "<i>(Masalan: <code>25</code> deb yozsangiz, 1-25 qismlar bepul, 26-qismdan boshlab ⭐ Premium bo‘ladi)</i>\n"
        "Barchasi bepul bo‘lishi uchun <code>0</code> deb yozing:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )

@router.message(EpisodeAccessState.free_up_to)
async def process_ep_access_threshold(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Raqam kiriting:")
        return

    free_up_to = int(text)
    data = await state.get_data()
    media_code = data["media_code"]
    await state.clear()

    await db.set_episodes_access_threshold(media_code, free_up_to)

    rule_str = f"1 dan {free_up_to}-qismgacha BEPUL, {free_up_to + 1}-qismdan boshlab ⭐ Premium" if free_up_to > 0 else "Barcha qismlar bepul"
    await message.answer(
        f"✅ <b>{data['title']}</b> [<code>{media_code}</code>] qismlari muvaffaqiyatli yangilandi!\n\n"
        f"Yangi tartib: <b>{rule_str}</b>",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(True)
    )

# ==================== MAJBURIY OBUNA KANALLARI (/channels) ====================

@router.message(Command("channels"))
@router.callback_query(F.data == "admin:channels")
async def show_required_channels(event: Message | CallbackQuery):
    """Majburiy a'zolik kanallari ro'yxati"""
    user_id = event.from_user.id
    if not await admin_check(user_id):
        return

    channels = await db.get_required_channels()
    text = "📢 <b>Majburiy Obuna Kanallari Boshqaruvi:</b>\n\n"
    buttons = []

    if not channels:
        text += "<i>Hozircha majburiy a'zolik kanallari belgilanmagan. Foydalanuvchilar to‘g‘ridan-to‘g‘ri bepul tomosha qila olishadi.</i>\n"
    else:
        text += "Foydalanuvchilar bepul kontentdan foydalanish uchun quyidagi kanallarga a'zo bo‘lishi shart:\n\n"
        for idx, ch in enumerate(channels, 1):
            name = ch.get("channel_name") or ch["channel_id"]
            text += f"{idx}. <b>{name}</b> (<code>{ch['channel_id']}</code>)\n"
            buttons.append([InlineKeyboardButton(text=f"❌ {name} ni o‘chirish", callback_data=f"del_ch:{ch['id']}")])

    buttons.append([InlineKeyboardButton(text="➕ Yangi kanal qo‘shish", callback_data="add_channel")])
    buttons.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="cancel_action")])
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)

    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=markup)
    else:
        await event.message.answer(text, parse_mode="HTML", reply_markup=markup)
        await event.answer()

@router.callback_query(F.data == "add_channel")
@router.message(Command("addchannel"))
async def start_add_channel(event: Message | CallbackQuery, state: FSMContext):
    user_id = event.from_user.id
    if not await admin_check(user_id):
        return

    await state.set_state(ChannelMgmtState.channel_id)
    text = (
        "➕ <b>Majburiy obuna uchun kanal qo‘shish:</b>\n\n"
        "1. Botni ushbu kanalga <b>Administrator</b> qilib qo‘shganingizga ishonch hosil qiling!\n"
        "2. Kanalning <b>@username</b> nomini yoki <b>ID raqamini</b> yuboring (Masalan: <code>@kino_olami</code>):"
    )
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    else:
        await event.message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
        await event.answer()

@router.message(ChannelMgmtState.channel_id)
async def process_channel_id(message: Message, state: FSMContext):
    ch_id = message.text.strip()
    await state.update_data(channel_id=ch_id)
    await state.set_state(ChannelMgmtState.channel_name)
    await message.answer("📝 Kanal nomini kiriting (Masalan: <code>Kino Olami Rasmiy</code>):", parse_mode="HTML")

@router.message(ChannelMgmtState.channel_name)
async def process_channel_name(message: Message, state: FSMContext):
    name = message.text.strip()
    await state.update_data(channel_name=name)
    await state.set_state(ChannelMgmtState.invite_link)
    await message.answer(
        "🔗 Kanalga taklif havolasini yuboring (Masalan: <code>https://t.me/kino_olami</code> yoki «-» deb yuboring):",
        parse_mode="HTML"
    )

@router.message(ChannelMgmtState.invite_link)
async def process_channel_link(message: Message, state: FSMContext):
    link = "" if message.text.strip() == "-" else message.text.strip()
    data = await state.get_data()
    await state.clear()

    ok = await db.add_required_channel(
        channel_id=data["channel_id"],
        channel_name=data["channel_name"],
        invite_link=link
    )
    if ok:
        await message.answer(
            f"🎉 <b>Kanal muvaffaqiyatli qo‘shildi!</b>\n\n"
            f"📢 <b>Nomi:</b> {data['channel_name']}\n"
            f"🔑 <b>ID/Username:</b> <code>{data['channel_id']}</code>\n\n"
            "Endi bepul foydalanuvchilar ushbu kanalga a'zo bo‘lmasdan bepul filmlarni ko‘ra olmaydilar.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(True)
        )
    else:
        await message.answer("❌ Kanalni saqlashda xatolik yuz berdi. Kanal ID takrorlanmaganligini tekshiring.", reply_markup=get_main_keyboard(True))

@router.callback_query(F.data.startswith("del_ch:"))
async def cb_del_channel(call: CallbackQuery):
    if not await db.is_admin(call.from_user.id):
        await call.answer("⛔️ Ruxsat berilmagan! Faqat adminlar kanalni o'chira oladi.", show_alert=True)
        return

    ch_id = call.data.split(":")[1]
    ok = await db.remove_required_channel(ch_id)
    if ok:
        await call.answer("✅ Kanal olib tashlandi!", show_alert=True)
        await show_required_channels(call)
    else:
        await call.answer("❌ O'chirishda xatolik!", show_alert=True)

# ==================== QISM QO'SHISH (/addepisode) ====================

@router.message(Command("addepisode"))
async def start_add_episode(message: Message, command: CommandObject, state: FSMContext):
    """Serial yoki animega navbatdagi qismni qo'shish"""
    user_id = message.from_user.id
    if not await admin_check(user_id):
        return

    args = (command.args or "").split()
    if len(args) >= 2:
        code = args[0]
        ep_num = int(args[1]) if args[1].isdigit() else 1
        media = await db.get_media_by_code(code)
        if not media:
            await message.answer(f"❌ <code>{code}</code> kodli media topilmadi!")
            return
        await state.update_data(media_code=code, episode_num=ep_num)
        await state.set_state(AddEpisodeState.file)
        await message.answer(
            f"🎬 <b>{media['title']}</b>\n"
            f"📺 <b>{ep_num}-qism</b> uchun video faylni yuboring:",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        return

    await state.set_state(AddEpisodeState.media_code)
    await message.answer(
        "📺 <b>Qism qo‘shish:</b>\nQaysi serial/animega qism qo‘shmoqchisiz? Uning <b>kodini</b> kiriting:\n<i>(Masalan: 12345)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )

@router.message(AddEpisodeState.media_code)
async def process_ep_media_code(message: Message, state: FSMContext):
    code = message.text.strip()
    media = await db.get_media_by_code(code)
    if not media:
        await message.answer(f"❌ <code>{code}</code> kodi bo‘yicha serial topilmadi. Qayta kiriting:")
        return

    episodes = await db.get_episodes(code)
    next_num = len(episodes) + 1
    await state.update_data(media_code=code)
    await state.set_state(AddEpisodeState.episode_num)
    await message.answer(
        f"✅ Serial: <b>{media['title']}</b>\n"
        f"Mavjud qismlar: {len(episodes)} ta.\n\n"
        f"Qo‘shilayotgan <b>qism raqamini</b> kiriting (Tavsiya: <code>{next_num}</code>):",
        parse_mode="HTML"
    )

@router.message(AddEpisodeState.episode_num)
async def process_ep_num(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Qism raqami faqat son bo'lishi kerak:")
        return

    await state.update_data(episode_num=int(text))
    await state.set_state(AddEpisodeState.file)
    await message.answer(f"📹 Endi <b>{text}-qism videosini</b> yuboring:", reply_markup=get_cancel_keyboard())

@router.message(AddEpisodeState.file, F.video | F.document)
async def process_ep_file(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not await admin_check(user_id):
        return

    if message.video:
        file_id = message.video.file_id
        file_name = message.video.file_name or ""
        file_type = "video"
    elif message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or ""
        file_type = "document"
    else:
        await message.answer("Iltimos, video yoki video-fayl yuboring!")
        return

    data = await state.get_data()
    ep_num = data.get("episode_num", 1)
    caption = message.caption or ""
    detected = extract_episode_num(caption, file_name)
    if detected is not None and detected > 0:
        ep_num = detected

    await db.add_episode(
        media_code=data["media_code"],
        episode_num=ep_num,
        season_num=1,
        title=f"{ep_num}-qism",
        file_id=file_id,
        file_type=file_type,
        is_premium=0
    )

    next_num = ep_num + 1
    await state.update_data(episode_num=next_num)

    finish_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yakunlash", callback_data="addep_finish")]
    ])

    await message.answer(
        f"🎉 <b>{data['media_code']}</b> uchun <b>{ep_num}-qism</b> muvaffaqiyatli saqlandi!\n\n"
        f"📹 Endi <b>{next_num}-qism videosini</b> yuboring (yoki yakunlang):",
        parse_mode="HTML",
        reply_markup=finish_kb
    )

@router.callback_query(F.data == "addep_finish")
async def cb_finish_add_episode(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer("✅ Qismlar qo‘shish muvaffaqiyatli yakunlandi!", reply_markup=get_main_keyboard(True))
    await call.answer()

# ==================== MEDIA O'CHIRISH (/deletemedia) ====================

@router.message(Command("deletemedia"))
@router.callback_query(F.data == "admin:deletemedia")
async def start_delete_media(event: Message | CallbackQuery, state: FSMContext):
    user_id = event.from_user.id
    if not await admin_check(user_id):
        return

    await state.set_state(DeleteMediaState.code)
    text = "🗑 <b>O‘chirmoqchi bo‘lgan medianing kodini kiriting:</b>"
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    else:
        await event.message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
        await event.answer()

@router.message(DeleteMediaState.code)
async def process_delete_code(message: Message, state: FSMContext):
    code = message.text.strip()
    await state.clear()

    ok = await db.delete_media(code)
    if ok:
        await message.answer(f"✅ <code>{code}</code> kodli media o‘chirildi!", parse_mode="HTML", reply_markup=get_main_keyboard(True))
    else:
        await message.answer(f"❌ <code>{code}</code> kodi bo‘yicha hech qanday media topilmadi.", parse_mode="HTML", reply_markup=get_main_keyboard(True))

# ==================== BEPUL / PULLIK SOZLASH (/access) ====================

@router.message(Command("access"))
@router.callback_query(F.data == "admin:access")
async def start_access_toggle(event: Message | CallbackQuery, state: FSMContext):
    user_id = event.from_user.id
    if not await admin_check(user_id):
        return

    await state.set_state(AccessMediaState.code)
    text = "🔒 <b>Kirish huquqini o‘zgartirmoqchi bo‘lgan media kodini kiriting:</b>\n<i>(Bepul bo‘lsa Premiumga, Premium bo‘lsa Bepulga aylanadi)</i>"
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    else:
        await event.message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
        await event.answer()

@router.message(AccessMediaState.code)
async def process_access_code(message: Message, state: FSMContext):
    code = message.text.strip()
    await state.clear()

    new_val = await db.toggle_media_access(code)
    if new_val is not None:
        status_text = "⭐ Faqat Premium" if new_val == 1 else "🆓 Bepul"
        await message.answer(
            f"✅ <code>{code}</code> kodli media holati muvaffaqiyatli o‘zgardi!\nYangi holat: <b>{status_text}</b>",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(True)
        )
    else:
        await message.answer(f"❌ <code>{code}</code> kodli media topilmadi.", parse_mode="HTML", reply_markup=get_main_keyboard(True))

# ==================== MEDIALAR RO'YXATI (/medialist) ====================

@router.message(Command("medialist"))
@router.callback_query(F.data == "admin:medialist")
async def show_medialist(event: Message | CallbackQuery):
    """Barcha medialar ro'yxati"""
    user_id = event.from_user.id
    if not await admin_check(user_id):
        return

    total = await db.get_total_media_count()
    items = await db.get_all_media(limit=15, offset=0)

    if not items:
        text = "📭 Hozircha bazada hech qanday media mavjud emas."
    else:
        text = f"📋 <b>Medialar ro‘yxati:</b> (Jami: {total} ta)\n\n"
        for idx, m in enumerate(items, 1):
            access = "⭐ Premium" if m["is_premium"] else "🆓 Bepul"
            safe_title = html.escape(m["title"])
            safe_code = html.escape(m["code"])
            text += f"{idx}. <b>{safe_title}</b> | Kod: <code>{safe_code}</code> | {access} | 👁 {m['views_count']}\n"

    target = event if isinstance(event, Message) else event.message
    await target.answer(text, parse_mode="HTML")
    if isinstance(event, CallbackQuery):
        await event.answer()

# ==================== KANALGA POST QILISH (AUTO-POSTER) ====================

async def post_media_to_channel(bot, media: dict, target_channel: str) -> bool:
    """Kanalga poster rasmi, to'liq tavsif va botga o'tish tugmasi bilan chiroyli post yuborish"""
    try:
        bot_info = await bot.get_me()
        bot_username = bot_info.username
        code = media["code"]
        title = media["title"]
        orig = f" ({media['original_title']})" if media.get("original_title") else ""
        prem_badge = "⭐ Premium (Faqat obunachilar uchun)" if media.get("is_premium") else "🆓 Bepul"
        cat = media.get("category", "kino").capitalize()

        post_text = (
            f"🎬 <b>{title}</b>{orig}\n\n"
            f"🔑 <b>Film kodi:</b> <code>{code}</code>\n"
            f"📂 <b>Kategoriya:</b> {cat}\n"
            f"💎 <b>Status:</b> {prem_badge}\n"
        )
        if media.get("year"):
            post_text += f"📅 <b>Yil:</b> {media['year']}\n"
        if media.get("genre"):
            post_text += f"🎭 <b>Janr:</b> {media['genre']}\n"
        if media.get("duration"):
            post_text += f"⏱ <b>Davomiyligi:</b> {media['duration']}\n"
        if media.get("language"):
            post_text += f"🌐 <b>Tili:</b> {media['language']}\n"
        if media.get("age_rating"):
            post_text += f"🔞 <b>Yosh chegarasi:</b> {media['age_rating']}\n"
        if media.get("description"):
            post_text += f"\n📝 <b>Syujet:</b>\n{media['description']}\n"

        post_text += f"\n🍿 <b>Filmni bot orqali tomosha qilish:</b>\n👇👇👇"

        share_url = f"https://t.me/{bot_username}?start={code}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Filmni tomosha qilish", url=share_url)],
            [InlineKeyboardButton(text="🤖 Bizning Kino Bot", url=f"https://t.me/{bot_username}")]
        ])

        if media.get("poster_file_id"):
            await bot.send_photo(
                chat_id=target_channel,
                photo=media["poster_file_id"],
                caption=post_text,
                parse_mode="HTML",
                reply_markup=kb
            )
        else:
            await bot.send_message(
                chat_id=target_channel,
                text=post_text,
                parse_mode="HTML",
                reply_markup=kb
            )
        return True
    except Exception:
        return False

@router.callback_query(F.data.startswith("chan_post:"))
async def cb_post_to_channel(call: CallbackQuery):
    if not await admin_check(call.from_user.id):
        return

    code = call.data.split(":")[1]
    media = await db.get_media_by_code(code)
    if not media:
        await call.answer("Media topilmadi!", show_alert=True)
        return

    post_channel = await db.get_setting("posting_channel")
    if not post_channel:
        await call.answer("Avval /setpostchannel orqali kanalni sozlang!", show_alert=True)
        return

    ok = await post_media_to_channel(call.bot, media, post_channel)
    if ok:
        await call.answer("✅ Kanalga muvaffaqiyatli post qilindi!", show_alert=True)
        await call.message.edit_reply_markup(reply_markup=None)
    else:
        await call.answer("❌ Kanalga post qilishda xatolik! Bot kanalda admin ekanligini tekshiring.", show_alert=True)

@router.message(Command("setpostchannel"))
@router.callback_query(F.data == "admin:setpostchannel")
async def start_set_post_channel(event: Message | CallbackQuery, state: FSMContext):
    user_id = event.from_user.id
    if not await admin_check(user_id):
        return

    current = await db.get_setting("posting_channel", "Belgilanmagan")
    await state.set_state(ChannelPostState.channel_id)
    text = (
        f"🚀 <b>Avtomatik Post Kanalini Sozlash:</b>\n\n"
        f"Joriy kanal: <b>{current}</b>\n\n"
        "Yangi kinolar post qilinadigan kanalning <b>@username</b> nomini yoki <b>ID raqamini</b> yuboring:\n"
        "<i>(Masalan: <code>@kino_olami</code> yoki <code>-100123456789</code>)</i>\n\n"
        "⚠️ <i>Bot ushbu kanalda post joylash huquqiga ega Administrator bo‘lishi kerak!</i>"
    )
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    else:
        await event.message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
        await event.answer()

@router.message(ChannelPostState.channel_id)
async def process_post_channel_id(message: Message, state: FSMContext):
    ch_id = message.text.strip()
    await state.clear()
    await db.set_setting("posting_channel", ch_id)

    await message.answer(
        f"✅ <b>Post kanali muvaffaqiyatli saqlandi!</b>\n\n"
        f"Kanal: <b>{ch_id}</b>\n"
        f"Endi yangi kinolar yuklanganda bitta tugma bilan ushbu kanalga chiroyli post qilib joylashingiz mumkin.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(True)
    )
