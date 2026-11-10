import math
import html
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from typing import Dict, Any, Optional

from database import db
from keyboards import (
    get_category_keyboard,
    get_category_items_keyboard,
    get_media_view_keyboard,
    get_episode_player_keyboard,
    get_cancel_keyboard,
    get_main_keyboard,
)
from utils.states import SearchMediaState
from utils.channel_check import check_user_channels_subscription, get_subscription_keyboard

router = Router()
ITEMS_PER_PAGE = 8

async def render_media_card(target: Message | CallbackQuery, media: Dict[str, Any], user_id: int):
    """
    Kino, Serial, Drama yoki Anime kartochkasini to'liq poster, ma'lumotlar va inline tugmalar bilan chiqarish.
    """
    user_is_prem = await db.is_user_premium(user_id)
    prem_status = "⭐ Premium (Faqat obunachilar uchun)" if media.get("is_premium") else "🆓 Bepul"
    episodes = await db.get_episodes(media["code"])
    is_fav = await db.is_favorite(user_id, media["code"])

    category_names = {
        "kino": "🎬 Film",
        "serial": "📺 Serial",
        "anime": "🍥 Anime",
        "drama": "🇰🇷 Drama"
    }
    cat_label = category_names.get(media.get("category", "").lower(), media.get("category", "").capitalize())

    title_safe = html.escape(media.get("title", ""))
    orig_safe = f" (<i>{html.escape(media['original_title'])}</i>)" if media.get("original_title") else ""
    code_safe = html.escape(media.get("code", ""))

    caption_lines = [
        f"🎬 <b>{title_safe}</b>{orig_safe}",
        "",
        f"🔑 <b>Kod:</b> <code>{code_safe}</code>",
        f"📂 <b>Kategoriya:</b> {cat_label}",
        f"💎 <b>Status:</b> {prem_status}",
    ]
    if media.get("year"):
        caption_lines.append(f"📅 <b>Yil:</b> {html.escape(str(media['year']))}")
    if media.get("genre"):
        caption_lines.append(f"🎭 <b>Janr:</b> {html.escape(media['genre'])}")
    if media.get("duration"):
        caption_lines.append(f"⏱ <b>Davomiyligi:</b> {html.escape(media['duration'])}")
    if media.get("language"):
        caption_lines.append(f"🌐 <b>Tili:</b> {html.escape(media['language'])}")
    if media.get("age_rating"):
        caption_lines.append(f"🔞 <b>Yosh chegarasi:</b> {html.escape(media['age_rating'])}")

    caption_lines.append(f"👁 <b>Ko'rishlar:</b> {media.get('views_count', 0)}")

    if episodes:
        caption_lines.append(f"\n📺 <b>Mavjud qismlar:</b> {len(episodes)} ta")

    if media.get("description"):
        desc = html.escape(media["description"])
        # Telegram foto izohi (caption) cheklovi: maksimal 1024 belgi
        if media.get("poster_file_id"):
            base_len = sum(len(line) + 1 for line in caption_lines)
            overhead = len("\n📝 <b>Haqida:</b>\n...")
            if base_len + overhead + len(desc) > 1000:
                avail = max(10, 1000 - base_len - overhead)
                desc = desc[:avail] + "..."
        caption_lines.append(f"\n📝 <b>Haqida:</b>\n{desc}")

    caption = "\n".join(caption_lines)
    keyboard = get_media_view_keyboard(
        code=media["code"],
        is_premium=bool(media.get("is_premium")),
        user_is_premium=user_is_prem,
        episodes=episodes,
        is_fav=is_fav
    )

    msg = target if isinstance(target, Message) else target.message

    if media.get("poster_file_id"):
        try:
            await msg.answer_photo(
                photo=media["poster_file_id"],
                caption=caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )
        except Exception:
            # Agar rasm yuklashda muammo bo'lsa matn sifatida yuborish
            await msg.answer(
                caption,
                parse_mode="HTML",
                reply_markup=keyboard
            )
    else:
        await msg.answer(
            caption,
            parse_mode="HTML",
            reply_markup=keyboard
        )

    if isinstance(target, CallbackQuery):
        await target.answer()

# ==================== KINO VA SERIALLAR BO'LIMI ====================

@router.message(Command("movies"))
@router.message(F.text == "🎬 Kino va seriallar")
async def cmd_movies(message: Message):
    """Kino va seriallar bo'limi"""
    await message.answer(
        "🎬 <b>Quyidagi toifalardan birini tanlang:</b>",
        parse_mode="HTML",
        reply_markup=get_category_keyboard()
    )

async def _show_category_page(target: Message | CallbackQuery, category: str, page: int = 1):
    total_count = await db.count_media_by_category(category)
    total_pages = math.ceil(total_count / ITEMS_PER_PAGE) if total_count > 0 else 1
    page = max(1, min(page, total_pages))

    offset = (page - 1) * ITEMS_PER_PAGE
    items = await db.get_media_by_category(category, limit=ITEMS_PER_PAGE, offset=offset)

    category_names = {
        "kino": "🎬 Filmlar",
        "serial": "📺 Seriallar",
        "anime": "🍥 Anime",
        "drama": "🇰🇷 Koreys va Xitoy Dramalari"
    }
    cat_title = category_names.get(category, category.capitalize())

    msg = target if isinstance(target, Message) else target.message

    if not items:
        text = f"{cat_title} bo'limida hozircha media mavjud emas."
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=get_category_keyboard())
            await target.answer()
        else:
            await msg.answer(text, reply_markup=get_category_keyboard())
        return

    text = f"📂 <b>{cat_title} ro‘yxati:</b>\n<i>(Jami: {total_count} ta)</i>\n\nKerakli filmni tanlang:"
    markup = get_category_items_keyboard(category, items, page=page, total_pages=total_pages)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        await target.answer()
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=markup)

# Asosiy menyudagi toifalar
@router.message(F.text == "🎬 Filmlar")
async def menu_filmlar(message: Message):
    await _show_category_page(message, "kino", 1)

@router.message(F.text == "📺 Seriallar")
async def menu_seriallar(message: Message):
    await _show_category_page(message, "serial", 1)

@router.message(F.text == "🇰🇷 Dramalar")
async def menu_dramalar(message: Message):
    await _show_category_page(message, "drama", 1)

@router.message(F.text == "🍥 Anime")
async def menu_anime(message: Message):
    await _show_category_page(message, "anime", 1)

@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()

@router.callback_query(F.data == "cat:back")
async def cb_category_back(call: CallbackQuery):
    if call.message.photo:
        await call.message.delete()
        await call.message.answer(
            "🎬 <b>Quyidagi toifalardan birini tanlang:</b>",
            parse_mode="HTML",
            reply_markup=get_category_keyboard()
        )
    else:
        try:
            await call.message.edit_text(
                "🎬 <b>Quyidagi toifalardan birini tanlang:</b>",
                parse_mode="HTML",
                reply_markup=get_category_keyboard()
            )
        except Exception:
            await call.message.answer(
                "🎬 <b>Quyidagi toifalardan birini tanlang:</b>",
                parse_mode="HTML",
                reply_markup=get_category_keyboard()
            )
    await call.answer()

@router.callback_query(F.data.startswith("ep_pg:"))
async def cb_episode_pagination(call: CallbackQuery):
    """Serial yoki anime qismlarini sahifalash (15 tadan qismlar)"""
    _, code, page_str = call.data.split(":")
    page = int(page_str)
    media = await db.get_media_by_code(code)
    if not media:
        await call.answer("Media topilmadi!", show_alert=True)
        return
    user_is_prem = await db.is_user_premium(call.from_user.id)
    episodes = await db.get_episodes(code)
    is_fav = await db.is_favorite(call.from_user.id, code)
    kb = get_media_view_keyboard(
        code=code,
        is_premium=bool(media.get("is_premium")),
        user_is_premium=user_is_prem,
        episodes=episodes,
        is_fav=is_fav,
        ep_page=page
    )
    try:
        await call.message.edit_reply_markup(reply_markup=kb)
    except Exception:
        pass
    await call.answer()

@router.callback_query(F.data.startswith("cat:"))
async def cb_select_category(call: CallbackQuery):
    category = call.data.split(":")[1]
    await _show_category_page(call, category, 1)

@router.callback_query(F.data.startswith("page:"))
async def cb_pagination(call: CallbackQuery):
    _, category, page_str = call.data.split(":")
    page = int(page_str)
    await _show_category_page(call, category, page)

@router.callback_query(F.data.startswith("view:"))
async def cb_view_media(call: CallbackQuery):
    """Media kartochkasini ko'rish"""
    code = call.data.split(":")[1]
    media = await db.get_media_by_code(code)
    if not media:
        await call.answer("❌ Ushbu media topilmadi!", show_alert=True)
        return

    await render_media_card(call, media, call.from_user.id)

# ==================== SEVIMLILAR VA ULARNI BOSHQARISH ====================

@router.callback_query(F.data.startswith("fav_add:"))
async def cb_fav_add(call: CallbackQuery):
    code = call.data.split(":")[1]
    await db.add_favorite(call.from_user.id, code)
    await call.answer("❤️ Sevimlilarga qo'shildi!", show_alert=False)

    media = await db.get_media_by_code(code)
    if media:
        user_is_prem = await db.is_user_premium(call.from_user.id)
        episodes = await db.get_episodes(code)
        kb = get_media_view_keyboard(
            code=code,
            is_premium=bool(media.get("is_premium")),
            user_is_premium=user_is_prem,
            episodes=episodes,
            is_fav=True
        )
        try:
            await call.message.edit_reply_markup(reply_markup=kb)
        except Exception:
            pass

@router.callback_query(F.data.startswith("fav_del:"))
async def cb_fav_del(call: CallbackQuery):
    code = call.data.split(":")[1]
    await db.remove_favorite(call.from_user.id, code)
    await call.answer("💔 Sevimlilardan olib tashlandi!", show_alert=False)

    media = await db.get_media_by_code(code)
    if media:
        user_is_prem = await db.is_user_premium(call.from_user.id)
        episodes = await db.get_episodes(code)
        kb = get_media_view_keyboard(
            code=code,
            is_premium=bool(media.get("is_premium")),
            user_is_premium=user_is_prem,
            episodes=episodes,
            is_fav=False
        )
        try:
            await call.message.edit_reply_markup(reply_markup=kb)
        except Exception:
            pass

@router.message(F.text == "❤️ Sevimlilar")
async def show_favorites(message: Message):
    """Foydalanuvchining sevimlilar ro'yxati"""
    user_id = message.from_user.id
    favs = await db.get_user_favorites(user_id, limit=20)
    if not favs:
        await message.answer(
            "❤️ <b>Sizning sevimlilar ro‘yxatingiz bo‘sh.</b>\n\n"
            "O‘zingizga yoqqan film yoki serial kartochkasida «❤️ Sevimlilarga qo'shish» tugmasini bossangiz, ular shu yerda saqlanadi.",
            parse_mode="HTML"
        )
        return

    text = f"❤️ <b>Sizning Sevimlilaringiz:</b> (Jami: {len(favs)} ta)\n\n"
    buttons = []
    for idx, m in enumerate(favs, 1):
        badge = "⭐ " if m["is_premium"] else "🆓 "
        text += f"{idx}. {badge}<b>{m['title']}</b> ({m.get('year') or '—'}) — Kod: <code>{m['code']}</code>\n"
        buttons.append([InlineKeyboardButton(text=f"🎬 {m['title']} [{m['code']}]", callback_data=f"view:{m['code']}")])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

# ==================== TOMOSHA TARIXI ====================

@router.message(F.text == "📚 Mening tarixim")
async def show_history(message: Message):
    """Foydalanuvchining ko'rishlar tarixi"""
    user_id = message.from_user.id
    history = await db.get_user_history(user_id, limit=15)
    if not history:
        await message.answer(
            "📚 <b>Siz hali hech qanday film tomosha qilmadingiz.</b>\n\n"
            "Kino yoki serial qismini ko'rish uchun faylni yuklab olganingizda, u avtomatik tarixingizda qayd etiladi.",
            parse_mode="HTML"
        )
        return

    text = f"📚 <b>Tomosha qilingan filmlar tarixi:</b>\n\n"
    buttons = []
    seen_codes = set()
    for idx, h in enumerate(history, 1):
        code = h["code"]
        if code not in seen_codes:
            seen_codes.add(code)
            watched_time = h.get("watched_at", "")[:16]
            text += f"{idx}. <b>{h['title']}</b> | Kod: <code>{code}</code>\n   🕒 <i>{watched_time}</i>\n"
            buttons.append([InlineKeyboardButton(text=f"🎬 {h['title']}", callback_data=f"view:{code}")])

    markup = InlineKeyboardMarkup(inline_keyboard=buttons[:10])
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

# ==================== MASHHUR VA YANGI FILMLAR ====================

@router.message(F.text == "🔥 Mashhur filmlar")
async def show_popular_movies(message: Message):
    """Eng ko'p ko'rilgan filmlar"""
    popular = await db.get_popular_media(limit=10)
    if not popular:
        await message.answer("🔥 Hozircha filmlar mavjud emas.")
        return

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    text = "🔥 <b>Eng mashhur filmlar (TOP-10):</b>\n\n"
    buttons = []
    for idx, m in enumerate(popular):
        rank = medals[idx] if idx < len(medals) else f"{idx+1}."
        badge = "⭐ " if m["is_premium"] else "🆓 "
        text += f"{rank} {badge}<b>{m['title']}</b> ({m.get('year') or '—'}) — Kod: <code>{m['code']}</code> (👁 {m['views_count']})\n"
        buttons.append([InlineKeyboardButton(text=f"{rank} {m['title']}", callback_data=f"view:{m['code']}")])

    text += "\n👇 Kerakli filmni ko‘rish uchun tugmani bosing yoki kodini yuboring!"
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

@router.message(F.text == "🆕 Yangi qo‘shilganlar")
async def show_recent_movies(message: Message):
    """Oxirgi qo'shilgan filmlar"""
    recent = await db.get_recent_media(limit=10)
    if not recent:
        await message.answer("🆕 Hozircha yangi qo'shilgan filmlar yo'q.")
        return

    text = "🆕 <b>Yangi qo‘shilgan kinolar va seriallar:</b>\n\n"
    buttons = []
    for idx, m in enumerate(recent, 1):
        badge = "⭐ " if m["is_premium"] else "🆓 "
        text += f"{idx}. {badge}<b>{m['title']}</b> ({m.get('year') or '—'}) — Kod: <code>{m['code']}</code>\n"
        buttons.append([InlineKeyboardButton(text=f"🆕 {m['title']}", callback_data=f"view:{m['code']}")])

    text += "\n👇 Kerakli filmni tanlang yoki kodini yozib yuboring:"
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

# ==================== FILM VA EPISODE YUKLASH ====================

@router.callback_query(F.data.startswith("download:"))
async def cb_download_media(call: CallbackQuery):
    """Filmni foydalanuvchiga yuborish va tarixga yozish"""
    code = call.data.split(":")[1]
    media = await db.get_media_by_code(code)
    if not media:
        await call.answer("❌ Media topilmadi!", show_alert=True)
        return

    user_is_prem = await db.is_user_premium(call.from_user.id)
    if media["is_premium"] and not user_is_prem:
        await call.answer("⭐ Ushbu filmni ko'rish uchun sizda Premium obuna bo'lishi kerak!", show_alert=True)
        return

    # Bepul foydalanuvchilar uchun majburiy obuna kanallarini tekshirish
    if not user_is_prem:
        sub_ok, unjoined = await check_user_channels_subscription(call.bot, call.from_user.id)
        if not sub_ok:
            await call.message.answer(
                "⚠️ <b>Hurmatli foydalanuvchi!</b>\n\n"
                "Filmni tomosha qilish uchun quyidagi homiy kanallarga a'zo bo‘ling:\n\n"
                "<i>A'zo bo‘lgach, «✅ A'zo bo'ldim / Tekshirish» tugmasini bosing:</i>",
                parse_mode="HTML",
                reply_markup=get_subscription_keyboard(unjoined)
            )
            await call.answer()
            return

    # Ko'rishlar sonini oshirish va tarixga saqlash
    await db.increment_media_views(code)
    await db.record_watch_history(call.from_user.id, code)

    orig = f" ({html.escape(media['original_title'])})" if media.get('original_title') else ""
    year_str = f" ({html.escape(str(media['year']))})" if media.get('year') else ""
    title_str = html.escape(media.get('title', 'Kino'))
    caption = (
        f"🎬 <b>{title_str}</b>{orig}{year_str}\n"
        f"🔑 Kod: <code>{html.escape(media['code'])}</code>\n\n"
        f"🍿 <i>Yoqimli tomosha tilaymiz! @FlixUzCinemaBot</i>"
    )
    is_protected = bool(media.get("is_premium", 0))

    status_msg = await call.message.answer("Yuklanmoqda...")
    try:
        if media.get("file_type") == "document":
            await call.message.answer_document(
                document=media["file_id"],
                caption=caption,
                parse_mode="HTML",
                protect_content=is_protected
            )
        else:
            try:
                await call.message.answer_video(
                    video=media["file_id"],
                    caption=caption,
                    parse_mode="HTML",
                    protect_content=is_protected
                )
            except Exception:
                await call.message.answer_document(
                    document=media["file_id"],
                    caption=caption,
                    parse_mode="HTML",
                    protect_content=is_protected
                )
        await status_msg.delete()
        await call.answer("✅ Film yuborildi!")
    except Exception as e:
        await status_msg.edit_text(f"❌ Faylni yuborishda xatolik yuz berdi: {e}")
        await call.answer()

@router.callback_query(F.data.startswith("ep_dl:"))
async def cb_download_episode(call: CallbackQuery):
    """Serial yoki anime qismini foydalanuvchiga yuborish va navigatsiya tugmalarini ko'rsatish"""
    ep_id = int(call.data.split(":")[1])
    
    import aiosqlite
    async with aiosqlite.connect(db.db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM episodes WHERE id = ?", (ep_id,)) as cur:
            row = await cur.fetchone()
            ep = dict(row) if row else None

    if not ep:
        await call.answer("❌ Qism topilmadi!", show_alert=True)
        return

    media = await db.get_media_by_code(ep["media_code"])
    user_is_prem = await db.is_user_premium(call.from_user.id)
    ep_is_prem = bool(ep.get("is_premium", 0))
    media_is_prem = bool(media.get("is_premium", 0)) if media else False

    # Agar qism yoki media pullik bo'lsa va foydalanuvchida premium bo'lmasa
    if (media_is_prem or ep_is_prem) and not user_is_prem:
        await call.answer(
            f"⭐ {ep['episode_num']}-qism faqat Premium obunachilar uchun!\nOldingi bepul qismlarni tomosha qilishingiz yoki Premium xarid qilishingiz mumkin.",
            show_alert=True
        )
        return

    # Bepul foydalanuvchilar uchun majburiy kanallarni tekshirish
    if not user_is_prem:
        sub_ok, unjoined = await check_user_channels_subscription(call.bot, call.from_user.id)
        if not sub_ok:
            await call.message.answer(
                "⚠️ <b>Hurmatli foydalanuvchi!</b>\n\n"
                f"{ep['episode_num']}-qismni tomosha qilish uchun quyidagi homiy kanallarga a'zo bo‘ling:\n\n"
                "<i>A'zo bo‘lgach, «✅ A'zo bo'ldim / Tekshirish» tugmasini bosing:</i>",
                parse_mode="HTML",
                reply_markup=get_subscription_keyboard(unjoined)
            )
            await call.answer()
            return

    await db.increment_media_views(ep["media_code"])
    await db.record_watch_history(call.from_user.id, ep["media_code"])

    title = html.escape(media['title']) if media else 'Serial'
    ep_extra = f" — {html.escape(ep['title'])}" if ep.get('title') else ""
    caption = (
        f"🎬 <b>{title}</b>\n"
        f"📺 <b>{ep['episode_num']}-qism{ep_extra}</b>\n\n"
        f"🍿 <i>Yoqimli tomosha tilaymiz! @FlixUzCinemaBot</i>"
    )

    prev_ep = await db.get_prev_episode(ep["media_code"], ep["episode_num"])
    next_ep = await db.get_next_episode(ep["media_code"], ep["episode_num"])
    prev_id = prev_ep["id"] if prev_ep else None
    next_id = next_ep["id"] if next_ep else None

    player_kb = get_episode_player_keyboard(ep["media_code"], prev_id, next_id)
    is_protected = bool(media_is_prem or ep_is_prem)
    file_type = ep.get("file_type", "video")

    status_msg = await call.message.answer("Yuklanmoqda...")
    try:
        if file_type == "document":
            await call.message.answer_document(
                document=ep["file_id"],
                caption=caption,
                parse_mode="HTML",
                reply_markup=player_kb,
                protect_content=is_protected
            )
        else:
            try:
                await call.message.answer_video(
                    video=ep["file_id"],
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=player_kb,
                    protect_content=is_protected
                )
            except Exception:
                await call.message.answer_document(
                    document=ep["file_id"],
                    caption=caption,
                    parse_mode="HTML",
                    reply_markup=player_kb,
                    protect_content=is_protected
                )
        await status_msg.delete()
        await call.answer("✅ Qism yuborildi!")
    except Exception as e:
        await status_msg.edit_text(f"❌ Faylni yuborishda xatolik: {e}")
        await call.answer()

@router.callback_query(F.data == "check_sub_status")
async def cb_check_sub_status(call: CallbackQuery):
    """Homiy kanallarga a'zolikni tekshirish tugmasi"""
    sub_ok, unjoined = await check_user_channels_subscription(call.bot, call.from_user.id)
    if sub_ok:
        await call.answer("🎉 A'zoligingiz tasdiqlandi! Endi barcha bepul filmlarni tomosha qilishingiz mumkin.", show_alert=True)
        try:
            await call.message.delete()
        except Exception:
            pass
        is_admin = await db.is_admin(call.from_user.id)
        await call.message.answer(
            "✅ <b>Xush kelibsiz!</b>\nTomosha qilmoqchi bo‘lgan kino kodini yuboring yoki menyudan tanlang:",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(is_admin)
        )
    else:
        await call.answer(
            f"❌ Siz hali {len(unjoined)} ta kanalga a'zo bo‘lmadingiz!\nIltimos, yuqoridagi kanallarga a'zo bo‘ling.",
            show_alert=True
        )

# ==================== QIDIRUV VA KOD BILAN TOPISH ====================

@router.message(F.text == "🔍 Film qidirish")
@router.message(F.text == "🔍 Qidiruv")
@router.callback_query(F.data == "action:search_code")
async def start_search_query(event: Message | CallbackQuery, state: FSMContext):
    """Film nomi yoki janri bo'yicha qidiruv"""
    await state.set_state(SearchMediaState.query)
    text = "🔍 Qidirayotgan kino, serial yoki anime <b>nomini</b> yoki <b>janrini</b> kiriting:"
    if isinstance(event, Message):
        await event.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
    else:
        await event.message.answer(text, parse_mode="HTML", reply_markup=get_cancel_keyboard())
        await event.answer()

@router.message(F.text == "🔢 Kod orqali topish")
async def start_code_search(message: Message, state: FSMContext):
    """Maxsus kod orqali topish"""
    await state.set_state(SearchMediaState.code_only)
    await message.answer(
        "🔢 Filmning <b>maxsus kodini</b> yuboring:\n<i>(Masalan: 12345, 101, AN01)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )

@router.message(SearchMediaState.code_only)
async def process_code_only(message: Message, state: FSMContext):
    code = (message.text or "").strip()
    if not code:
        await message.answer("Iltimos, kodni matn shaklida yuboring:")
        return

    await state.clear()
    is_admin = await db.is_admin(message.from_user.id)

    media = await db.get_media_by_code(code)
    if media:
        await render_media_card(message, media, message.from_user.id)
    else:
        safe_code = html.escape(code)
        await message.answer(
            f"❌ «<b>{safe_code}</b>» kodi bo‘yicha hech qanday film topilmadi.\nKodni to‘g‘ri yozganingizga ishonch hosil qiling.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(is_admin)
        )

@router.message(SearchMediaState.query)
async def process_search_query(message: Message, state: FSMContext):
    """Qidiruv so'rovini qabul qilish va natijalarni chiqarish"""
    query = (message.text or "").strip()
    if not query:
        await message.answer("Iltimos, qidiruv so'rovini matn ko'rinishida yuboring:")
        return

    await state.clear()
    is_admin = await db.is_admin(message.from_user.id)

    # 1. Avval aniq kod bo'yicha tekshiramiz
    exact_media = await db.get_media_by_code(query)
    if exact_media:
        await render_media_card(message, exact_media, message.from_user.id)
        return

    # 2. Nom, original nom yoki janr bo'yicha qidirish
    results = await db.search_media(query, limit=10)
    safe_query = html.escape(query)
    if not results:
        await message.answer(
            f"❌ «<b>{safe_query}</b>» bo'yicha hech qanday natija topilmadi.\nTo‘g‘ri nom yoki kodni yuboring.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(is_admin)
        )
        return

    text = f"🔍 «<b>{safe_query}</b>» bo'yicha topilgan natijalar:\n\n"
    buttons = []
    for idx, r in enumerate(results, 1):
        badge = "⭐ " if r["is_premium"] else "🆓 "
        title_s = html.escape(r["title"])
        text += f"{idx}. {badge}<b>{title_s}</b> ({r.get('year') or '—'}) — Kod: <code>{r['code']}</code>\n"
        buttons.append([InlineKeyboardButton(text=f"🎬 {r['title']} [{r['code']}]", callback_data=f"view:{r['code']}")])

    text += "\n👇 Tomosha qilish uchun film tugmasini bosing yoki uning <b>kodini</b> yuboring!"
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, parse_mode="HTML", reply_markup=markup)

# ==================== ODDIY MATN YUBORILGANDA (KOD TEKSHIRUVI) ====================

@router.message(F.text & ~F.text.startswith("/"))
async def auto_code_lookup(message: Message):
    text = message.text.strip()

    # Asosiy menyu tugmalari bo'lsa o'tkazib yuboramiz
    reserved = [
        "🎬 Filmlar", "📺 Seriallar", "🇰🇷 Dramalar", "🍥 Anime",
        "🔍 Film qidirish", "🔢 Kod orqali topish",
        "🔥 Mashhur filmlar", "🆕 Yangi qo‘shilganlar",
        "❤️ Sevimlilar", "📚 Mening tarixim",
        "💡 Film so‘rash", "⭐ Premium",
        "👤 Profil", "⚙️ Sozlamalar",
        "📱 Admin Mini App", "⚙️ Admin panel", "❌ Bekor qilish"
    ]
    if text in reserved:
        return

    # 1. Kod bo'yicha qidiruv
    if len(text) <= 30:
        media = await db.get_media_by_code(text)
        if media:
            await render_media_card(message, media, message.from_user.id)
            return

    # 2. Agar kod topilmasa, nom bo'yicha qidirib ko'ramiz
    results = await db.search_media(text, limit=6)
    if results:
        res_text = f"🔍 «<b>{text}</b>» bo‘yicha topilgan natijalar:\n\n"
        buttons = []
        for idx, r in enumerate(results, 1):
            badge = "⭐ " if r["is_premium"] else "🆓 "
            res_text += f"{idx}. {badge}<b>{r['title']}</b> — Kod: <code>{r['code']}</code>\n"
            buttons.append([InlineKeyboardButton(text=f"🎬 {r['title']} [{r['code']}]", callback_data=f"view:{r['code']}")])
        res_text += "\nTomosha qilish uchun kino kodini yuboring yoki quyidagi tugmani bosing:"
        markup = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.answer(res_text, parse_mode="HTML", reply_markup=markup)
    else:
        await message.answer(
            f"❌ «<b>{text}</b>» kodi yoki nomi bo'yicha kino topilmadi.\n"
            "To'g'ri kodni yuboring yoki menyudagi bo'limlardan foydalaning.",
            parse_mode="HTML"
        )
