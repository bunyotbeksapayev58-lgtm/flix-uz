import hashlib
from aiogram import Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from database import db

router = Router()

@router.inline_query()
async def inline_search(inline_query: InlineQuery):
    """
    Do'stlar bilan chatda inline qidiruv (@FlixUzCinemaBot <nom/kod>)
    """
    query = inline_query.query.strip()
    bot_info = await inline_query.bot.get_me()
    bot_username = bot_info.username

    if not query:
        # Bo'sh qidiruvda eng mashhur filmlarni ko'rsatamiz
        items = await db.get_popular_media(limit=10)
    else:
        items = await db.search_media(query, limit=15)

    results = []
    for m in items:
        code = m["code"]
        title = m["title"]
        year = f" ({m['year']})" if m.get("year") else ""
        prem_badge = "⭐ Premium" if m.get("is_premium") else "🆓 Bepul"
        cat = m.get("category", "kino").capitalize()

        share_url = f"https://t.me/{bot_username}?start={code}"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎬 Filmni tomosha qilish", url=share_url)]
        ])

        caption_text = (
            f"🎬 <b>{title}</b>{year}\n\n"
            f"🔑 <b>Kodi:</b> <code>{code}</code>\n"
            f"📂 <b>Kategoriya:</b> {cat}\n"
            f"💎 <b>Status:</b> {prem_badge}\n"
            f"🎭 <b>Janr:</b> {m.get('genre') or '—'}\n"
            f"⏱ <b>Davomiyligi:</b> {m.get('duration') or '—'}\n\n"
            f"🍿 <i>Ushbu filmni bot orqali tomosha qilish uchun quyidagi tugmani bosing:</i>"
        )

        item_id = hashlib.md5(f"{code}_{m.get('id', 0)}".encode()).hexdigest()

        if m.get("poster_file_id"):
            try:
                results.append(
                    InlineQueryResultCachedPhoto(
                        id=item_id,
                        photo_file_id=m["poster_file_id"],
                        title=f"{title}{year} [{code}]",
                        description=f"{cat} | {prem_badge} | Janr: {m.get('genre') or '—'}",
                        caption=caption_text,
                        parse_mode="HTML",
                        reply_markup=kb
                    )
                )
                continue
            except Exception:
                pass

        # Agar poster bo'lmasa yoki xatolik bo'lsa Article ko'rinishida
        results.append(
            InlineQueryResultArticle(
                id=item_id,
                title=f"{title}{year}",
                description=f"Kod: {code} | {cat} | {prem_badge}",
                input_message_content=InputTextMessageContent(
                    message_text=caption_text,
                    parse_mode="HTML"
                ),
                reply_markup=kb
            )
        )

    await inline_query.answer(
        results=results,
        cache_time=30,
        is_personal=True
    )
