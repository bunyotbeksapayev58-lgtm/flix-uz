import os
from pathlib import Path
from dotenv import load_dotenv

# .env faylni yuklash
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
raw_super_admin = os.getenv("SUPER_ADMIN_ID", "0").strip()
SUPER_ADMIN_IDS: list[int] = []
for part in raw_super_admin.replace(";", ",").split(","):
    part = part.strip()
    if part.isdigit():
        val = int(part)
        if val > 0:
            SUPER_ADMIN_IDS.append(val)

SUPER_ADMIN_ID: int = SUPER_ADMIN_IDS[0] if SUPER_ADMIN_IDS else 0
SUPPORT_USERNAME: str = os.getenv("SUPPORT_USERNAME", "@admin_support").strip()

CHANNELS_RAW = os.getenv("CHANNELS_TO_CHECK", "").strip()
CHANNELS_TO_CHECK: list[str] = [ch.strip() for ch in CHANNELS_RAW.split(",") if ch.strip()]

PREMIUM_PRICES = {
    "1_month": os.getenv("PREMIUM_PRICE_1MONTH", "15 000 so'm"),
    "3_months": os.getenv("PREMIUM_PRICE_3MONTHS", "40 000 so'm"),
    "1_year": os.getenv("PREMIUM_PRICE_1YEAR", "120 000 so'm"),
}

# Ma'lumotlar bazasi yo'li (Persistent Disk va muhit o'zgaruvchilari qo'llab-quvvatlanadi)
raw_db_path = os.getenv("DATABASE_PATH", os.getenv("DB_PATH", "")).strip()
if raw_db_path:
    DB_PATH = Path(raw_db_path)
else:
    DB_PATH = BASE_DIR / "database" / "cinema.db"

# Papkasi mavjud bo'lmasa, avtomatik yaratish
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Avtomatik bulutli zaxiralash (Telegram Backup Channel yoki Super Admin)
BACKUP_CHANNEL_RAW = os.getenv("BACKUP_CHANNEL_ID", "").strip()
BACKUP_CHANNEL_ID: int | None = None
if BACKUP_CHANNEL_RAW:
    clean_bc = BACKUP_CHANNEL_RAW.replace(" ", "")
    if clean_bc.lstrip("-").isdigit():
        BACKUP_CHANNEL_ID = int(clean_bc)

AUTO_BACKUP_ENABLED: bool = os.getenv("AUTO_BACKUP_ENABLED", "true").lower() in ("true", "1", "yes")

# Mini App (WebApp) Sozlamalari
WEBAPP_HOST: str = os.getenv("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT: int = int(os.getenv("PORT", os.getenv("WEBAPP_PORT", "8080")))
WEBAPP_URL: str = os.getenv("WEBAPP_URL", f"http://localhost:{WEBAPP_PORT}").strip()
