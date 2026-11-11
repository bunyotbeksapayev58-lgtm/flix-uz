import os
import shutil
import sqlite3
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from aiogram import Bot
from aiogram.types import FSInputFile
from config import (
    DB_PATH,
    BASE_DIR,
    SUPER_ADMIN_ID,
    SUPER_ADMIN_IDS,
    BACKUP_CHANNEL_ID,
    AUTO_BACKUP_ENABLED
)

logger = logging.getLogger(__name__)

BACKUP_DIR = BASE_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

def _sqlite_atomic_backup(src_path: str, dst_path: Path):
    """SQLite Online Backup API orqali tranzaksiyalarni buzmasdan atomik nusxa olish"""
    with sqlite3.connect(src_path) as src:
        with sqlite3.connect(str(dst_path)) as dst:
            src.backup(dst)

def verify_sqlite_database(db_file: Path) -> Tuple[bool, str, int, int]:
    """
    SQLite fayli butunligini va FlixUz bazasi ekanligini tekshirish.
    Qaytaradi: (is_valid, message, media_count, user_count)
    """
    if not db_file.exists() or db_file.stat().st_size == 0:
        return False, "Fayl bo'sh yoki topilmadi", 0, 0

    try:
        with sqlite3.connect(str(db_file)) as conn:
            cursor = conn.cursor()
            # 1. Butunlik tekshiruvi
            cursor.execute("PRAGMA integrity_check;")
            res = cursor.fetchone()
            if not res or res[0] != "ok":
                return False, f"Baza yaxlit emas: {res[0] if res else 'noma lum'}", 0, 0

            # 2. Kerakli jadvallar borligini tekshirish
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {row[0] for row in cursor.fetchall()}
            if "media" not in tables or "users" not in tables:
                return False, "Faylda zaruriy jadvallar (media, users) topilmadi", 0, 0

            cursor.execute("SELECT COUNT(*) FROM media;")
            media_cnt = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM users;")
            user_cnt = cursor.fetchone()[0]

            return True, "Baza yaroqli", media_cnt, user_cnt
    except Exception as e:
        return False, f"Tekshirishda xatolik: {e}", 0, 0

async def perform_database_backup_file() -> Optional[Path]:
    """Mahalliy xotirada atomik .db zaxira fayli yaratadi"""
    if not DB_PATH.exists():
        logger.warning("Baza fayli topilmadi, zaxira olinmadi.")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"cinema_backup_{timestamp}.db"

    try:
        await asyncio.to_thread(_sqlite_atomic_backup, str(DB_PATH), backup_file)
        
        # Eski lokal nusxalarni tozalash (oxirgi 10 tasini qoldirish)
        all_backups = sorted(BACKUP_DIR.glob("cinema_backup_*.db"), key=lambda f: f.stat().st_mtime)
        if len(all_backups) > 10:
            for old_f in all_backups[:-10]:
                try:
                    old_f.unlink()
                except Exception:
                    pass

        return backup_file
    except Exception as e:
        logger.error(f"Lokal zaxira olishda xatolik: {e}", exc_info=True)
        return None

async def send_backup_to_telegram(bot: Bot, backup_file: Path, reason: str = "avtomatik") -> bool:
    """Zaxira faylini Telegram kanalga yoki Super Adminga yuboradi"""
    if not backup_file.exists():
        return False

    is_valid, msg, media_cnt, user_cnt = verify_sqlite_database(backup_file)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    size_kb = round(backup_file.stat().st_size / 1024, 1)

    caption = (
        f"💾 <b>#CINEMA_DB_BACKUP</b>\n\n"
        f"🎬 <b>FlixUz Baza Zaxirasi</b>\n"
        f"📅 <b>Vaqt:</b> {now_str}\n"
        f"📊 <b>Kinolar/Seriallar:</b> {media_cnt} ta\n"
        f"👥 <b>Foydalanuvchilar:</b> {user_cnt} ta\n"
        f"📁 <b>Hajmi:</b> {size_kb} KB\n"
        f"💡 <b>Sabab:</b> {reason}\n\n"
        f"<i>Server qayta ishga tushganda yoki yangi deploy qilinganda ushbu fayl orqali barcha kinolarni 1 soniyada tiklash mumkin.</i>"
    )

    sent = False

    # 1. Agar maxsus zaxira kanali ko'rsatilgan bo'lsa (Kanalga yuborish va PIN qilish)
    if BACKUP_CHANNEL_ID:
        try:
            doc = FSInputFile(str(backup_file), filename=backup_file.name)
            sent_msg = await bot.send_document(
                chat_id=BACKUP_CHANNEL_ID,
                document=doc,
                caption=caption,
                parse_mode="HTML"
            )
            # Kanalga mahkamlash (kelgusida avtomatik tiklab olish uchun)
            try:
                await bot.pin_chat_message(
                    chat_id=BACKUP_CHANNEL_ID,
                    message_id=sent_msg.message_id,
                    disable_notification=True
                )
            except Exception as pe:
                logger.debug(f"Kanalda xabarni pin qilish imkoni bo'lmadi: {pe}")
            sent = True
            logger.info(f"✅ Baza zaxirasi zaxira kanaliga ({BACKUP_CHANNEL_ID}) yuborildi.")
        except Exception as e:
            logger.error(f"Zaxira kanaliga yuborishda xatolik: {e}")

    # 2. Agar kanalga yuborilmagan bo'lsa yoki Super Adminga ham yuborish kerak bo'lsa
    target_admin = SUPER_ADMIN_ID or (SUPER_ADMIN_IDS[0] if SUPER_ADMIN_IDS else None)
    if target_admin and target_admin > 0:
        try:
            doc = FSInputFile(str(backup_file), filename=backup_file.name)
            await bot.send_document(
                chat_id=target_admin,
                document=doc,
                caption=caption,
                parse_mode="HTML"
            )
            sent = True
            logger.info(f"✅ Baza zaxirasi Super Adminga ({target_admin}) yuborildi.")
        except Exception as e:
            logger.debug(f"Super adminga zaxira yuborishda xatolik: {e}")

    return sent

async def auto_backup_trigger(bot: Bot, reason: str = "media_ozgarishi"):
    """Yangi media qo'shilganda yoki muhim amaliyotda avtomatik orqa fonda zaxiralash"""
    if not AUTO_BACKUP_ENABLED:
        return
    try:
        backup_file = await perform_database_backup_file()
        if backup_file:
            await send_backup_to_telegram(bot, backup_file, reason=reason)
    except Exception as e:
        logger.error(f"Avtomatik zaxiralashda xatolik: {e}")

async def auto_restore_on_startup(bot: Bot) -> bool:
    """
    Bot ishga tushganda tekshiradi:
    Agar yangi deploy bo'lib, baza fayli bo'sh bo'lsa,
    Telegram zaxira kanalidan oxirgi pin qilingan zaxirani yuklab olib avtomatik tiklaydi!
    """
    if not BACKUP_CHANNEL_ID:
        return False

    # Agar lokal baza mavjud bo'lib, ichida kinolar bo'lsa, tiklash shart emas
    if DB_PATH.exists() and DB_PATH.stat().st_size > 0:
        is_valid, _, media_cnt, _ = verify_sqlite_database(DB_PATH)
        if is_valid and media_cnt > 0:
            logger.info(f"💾 Lokal baza to'liq holatda ({media_cnt} ta media mavjud). Avtomatik tiklash talab etilmadi.")
            return True

    logger.warning("⚠️ Lokal baza bo'sh yoki yangi container yaratilgan! Zaxira kanalidan tiklash boshlanmoqda...")
    try:
        chat = await bot.get_chat(BACKUP_CHANNEL_ID)
        pinned = chat.pinned_message
        if not pinned or not pinned.document:
            logger.warning("Zaxira kanalida mahkamlangan (pinned) zaxira hujjati topilmadi.")
            return False

        temp_restore = BACKUP_DIR / "temp_restore.db"
        await bot.download(pinned.document.file_id, destination=temp_restore)

        is_valid, msg, media_cnt, user_cnt = verify_sqlite_database(temp_restore)
        if not is_valid:
            logger.error(f"Yuklab olingan zaxira fayli yaroqsiz: {msg}")
            if temp_restore.exists():
                temp_restore.unlink()
            return False

        # Asosiy bazaga ko'chirish
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(temp_restore, DB_PATH)
        temp_restore.unlink()

        logger.info(f"🎉 BAZA MUVAFFAQIYATLI TIKLANDI! {media_cnt} ta media, {user_cnt} ta foydalanuvchi qaytarildi.")
        return True
    except Exception as e:
        logger.error(f"Zaxira kanalidan avtomatik tiklashda xatolik: {e}", exc_info=True)
        return False

async def restore_database_from_file_path(target_file: Path) -> Tuple[bool, str]:
    """Berilgan fayldan bazani to'liq almashtirib tiklash"""
    is_valid, msg, media_cnt, user_cnt = verify_sqlite_database(target_file)
    if not is_valid:
        return False, msg

    try:
        # Avval joriy bazadan avariya nusxasi olib qo'yamiz
        if DB_PATH.exists():
            emergency_file = BACKUP_DIR / f"cinema_before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            shutil.copy2(DB_PATH, emergency_file)

        shutil.copy2(target_file, DB_PATH)
        return True, f"Baza muvaffaqiyatli tiklandi! Kinolar: {media_cnt} ta, Foydalanuvchilar: {user_cnt} ta."
    except Exception as e:
        return False, f"Faylni almashtirishda xatolik yuz berdi: {e}"
