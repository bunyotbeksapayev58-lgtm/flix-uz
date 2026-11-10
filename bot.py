import asyncio
import logging
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand, BotCommandScopeDefault
from aiohttp import web

from config import BOT_TOKEN, WEBAPP_HOST, WEBAPP_PORT, WEBAPP_URL
from database import db
from handlers import setup_routers
from middlewares import BanCheckMiddleware
from middlewares.throttling import ThrottlingMiddleware
from webapp import create_admin_app
from workers.scheduler import start_background_workers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def set_default_commands(bot: Bot):
    """Telegram menyusida chiqadigan barcha buyruqlar ro'yxati (Master Checklist)"""
    commands = [
        BotCommand(command="start", description="Botni ishga tushirish"),
        BotCommand(command="menu", description="Asosiy menyu"),
        BotCommand(command="movies", description="Kino va seriallar"),
        BotCommand(command="profile", description="Shaxsiy profil va referallar"),
        BotCommand(command="premium", description="Premium obuna"),
        BotCommand(command="promo", description="Promokod kiritish"),
        BotCommand(command="support", description="Yordam markazi"),
        BotCommand(command="settings", description="Sozlamalar va til"),
        BotCommand(command="help", description="Qo'llanma"),
        BotCommand(command="about", description="Bot haqida"),
        BotCommand(command="privacy", description="Maxfiylik siyosati"),
        BotCommand(command="terms", description="Foydalanish shartlari"),
        BotCommand(command="admin", description="Admin paneli"),
        BotCommand(command="addmedia", description="Media qo‘shish"),
        BotCommand(command="deletemedia", description="Media olib tashlash"),
        BotCommand(command="medialist", description="Kino va seriallar ro‘yxati"),
        BotCommand(command="users", description="Foydalanuvchilar ro‘yxati"),
        BotCommand(command="blockuser", description="Foydalanuvchini bloklash"),
        BotCommand(command="unblockuser", description="Blokdan chiqarish"),
        BotCommand(command="stats", description="Umumiy statistika"),
        BotCommand(command="monthly", description="Oylik foydalanuvchilar"),
        BotCommand(command="addadmin", description="Admin qo‘shish"),
        BotCommand(command="removeadmin", description="Adminni olib tashlash"),
        BotCommand(command="access", description="Bepul va pullik media boshqaruvi"),
        BotCommand(command="batchupload", description="Ommaviy qismlarni bir vaqtda yuklash"),
        BotCommand(command="epaccess", description="Qismlar narxini (bepul/pullik) sozlash"),
        BotCommand(command="channels", description="Majburiy obuna kanallari"),
        BotCommand(command="requestmovie", description="Film buyurtma qilish / so'rash"),
        BotCommand(command="requests", description="Kino buyurtmalari (Admin)"),
        BotCommand(command="setpostchannel", description="Kanalga post sozlash (Admin)"),
        BotCommand(command="premium_settings", description="Premium narxlari va to'lov admini (Admin)"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

async def main():
    if not BOT_TOKEN or BOT_TOKEN == "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ":
        logger.error("❌ XATOLIK: .env faylida BOT_TOKEN ko'rsatilmagan! Iltimos, .env faylni to'ldiring.")
        print("\n=======================================================")
        print("XATOLIK: BOT_TOKEN topilmadi!")
        print("1. .env fayliga @BotFather dan olingan bot tokenni kiriting.")
        print("2. SUPER_ADMIN_ID ga o'zingizning Telegram ID raqamingizni yozing.")
        print("=======================================================\n")
        return

    # Ma'lumotlar bazasini ishga tushirish
    await db.init_db()
    logger.info("✅ Ma'lumotlar bazasi tayyorlandi.")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # Middleware-larni ulash
    throttle_middleware = ThrottlingMiddleware(rate_limit=0.5)
    dp.message.outer_middleware(throttle_middleware)
    dp.callback_query.outer_middleware(throttle_middleware)

    ban_middleware = BanCheckMiddleware()
    dp.message.outer_middleware(ban_middleware)
    dp.callback_query.outer_middleware(ban_middleware)

    # Routerlarni ulash
    dp.include_router(setup_routers())

    # Global xatoliklarni ushlovchi handler (Telegram BadRequest, Entity parsing xatolarini ushlash)
    @dp.error()
    async def global_error_handler(event, exception=None):
        err = exception or getattr(event, "exception", None)
        logger.error(f"⚠️ Global Telegram handler xatoligi: {err}", exc_info=True)
        return True

    # Buyruqlar menyusini sozlash
    try:
        await set_default_commands(bot)
    except Exception as e:
        logger.warning(f"Buyruqlarni o'rnatishda xatolik: {e}")

    # Admin Mini App Web Serverini ishga tushirish
    admin_web_app = create_admin_app(bot)
    runner = web.AppRunner(admin_web_app)
    await runner.setup()
    site = web.TCPSite(runner, host=WEBAPP_HOST, port=WEBAPP_PORT)
    await site.start()
    logger.info(f"🌐 Admin Mini App serveri ishga tushdi: {WEBAPP_URL} (Port: {WEBAPP_PORT})")

    logger.info("🚀 CineVerse Bot ishga tushdi va xabarlarni kutmoqda...")
    
    # Fon vazifalarini ishga tushirish (Obunalar nazorati va Database backup)
    worker_task = asyncio.create_task(start_background_workers(bot))

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        worker_task.cancel()
        await runner.cleanup()
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
