import asyncio
import sqlite3
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from aiogram import Bot
import aiosqlite
from database import db
from config import DB_PATH, BASE_DIR

logger = logging.getLogger(__name__)
BACKUP_DIR = BASE_DIR / "backups"

def _sqlite_atomic_backup(src_path: str, dst_path: Path):
    with sqlite3.connect(src_path) as src, sqlite3.connect(str(dst_path)) as dst:
        src.backup(dst)

async def check_expiring_subscriptions(bot: Bot):
    """Obunasi tugayotgan va tugagan foydalanuvchilarni tekshirish (Spamsiz, bir martalik eslatma)"""
    try:
        now = datetime.now(timezone.utc)
        three_days_later = (now + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        async with aiosqlite.connect(db.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            
            # 1. Muddati tugaganlarni aniqlash va o'chirish
            async with conn.execute(
                "SELECT id, first_name FROM users WHERE is_premium = 1 AND premium_until <= ?",
                (now_str,)
            ) as cur:
                expired_users = await cur.fetchall()

            for u in expired_users:
                await db.remove_user_premium(u["id"])
                try:
                    await bot.send_message(
                        u["id"],
                        "⚠️ <b>Hurmatli foydalanuvchi!</b>\n\nSizning Premium obuna muddatingiz yakunlandi.\n"
                        "Barcha filmlarni yana cheklovlarsiz ko'rish uchun /premium buyrug'i orqali obunani yangilashingiz mumkin.",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

            # 2. 3 kun qolganlarni ogohlantirish (faqat bir marta yuboriladi: reminder_sent = 0)
            async with conn.execute("""
                SELECT id FROM users 
                WHERE is_premium = 1 AND reminder_sent = 0 AND premium_until > ? AND premium_until <= ?
            """, (now_str, three_days_later)) as cur:
                warning_users = await cur.fetchall()

            for u in warning_users:
                try:
                    await bot.send_message(
                        u["id"],
                        "⏳ <b>Eslatma:</b> Premium obunangiz tugashiga 3 kundan kam vaqt qoldi!\n"
                        "Obunani uzaytirish uchun /premium buyrug'idan foydalanishingiz mumkin.",
                        parse_mode="HTML"
                    )
                    await conn.execute("UPDATE users SET reminder_sent = 1 WHERE id = ?", (u["id"],))
                    await conn.commit()
                except Exception:
                    pass

    except Exception as e:
        logger.error(f"Subscription checker error: {e}")

async def perform_database_backup():
    """Ma'lumotlar bazasini xavfsiz va atomik zaxiralash (SQLite Online Backup API)"""
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_file = BACKUP_DIR / f"cinema_backup_{timestamp}.db"

        await asyncio.to_thread(_sqlite_atomic_backup, db.db_path, backup_file)
        logger.info(f"💾 Avtomatik atomik baza zaxirasi yaratildi: {backup_file.name}")

        # Eski zaxiralarni tozalash (faqat oxirgi 10 tasini saqlash)
        all_backups = sorted(BACKUP_DIR.glob("cinema_backup_*.db"), key=lambda f: f.stat().st_mtime)
        if len(all_backups) > 10:
            for old_f in all_backups[:-10]:
                old_f.unlink()
    except Exception as e:
        logger.error(f"Database backup error: {e}")

async def start_background_workers(bot: Bot):
    """Fon vazifalarini va rejalashtiruvchini (Scheduler) ishga tushirish"""
    logger.info("⚙️ Background Scheduler & Workers ishga tushdi...")
    while True:
        try:
            await check_expiring_subscriptions(bot)
            await perform_database_backup()
        except Exception as e:
            logger.error(f"Scheduler worker exception: {e}")
        # Har 6 soatda bir marta tekshiradi
        await asyncio.sleep(6 * 3600)
