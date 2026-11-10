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

DB_PATH = BASE_DIR / "database" / "cinema.db"

# Mini App (WebApp) Sozlamalari
WEBAPP_HOST: str = os.getenv("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT: int = int(os.getenv("PORT", os.getenv("WEBAPP_PORT", "8080")))
WEBAPP_URL: str = os.getenv("WEBAPP_URL", f"http://localhost:{WEBAPP_PORT}").strip()
