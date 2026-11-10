import os
import sys
import sqlite3
import asyncio
from datetime import datetime, timezone
from pathlib import Path

# Asosiy jildni import qilish
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from config import DB_PATH
import aiosqlite

def _sqlite_backup(src_path: str, dst_path: Path):
    with sqlite3.connect(src_path) as src, sqlite3.connect(str(dst_path)) as dst:
        src.backup(dst)

async def run_backup():
    backup_dir = BASE_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"manual_backup_{timestamp}.db"
    
    print(f"📦 Atomik baza zaxiralash boshlandi: {DB_PATH} -> {dest}")
    await asyncio.to_thread(_sqlite_backup, DB_PATH, dest)
    
    # Baza yaxlitligini tekshirish (PRAGMA integrity_check)
    async with aiosqlite.connect(dest) as db:
        async with db.execute("PRAGMA integrity_check") as cur:
            res = await cur.fetchone()
            print(f"🔍 Baza yaxlitligi tekshiruvi: {res[0] if res else 'Unknown'}")

    print(f"✅ Baza muvaffaqiyatli saqlandi! Hajmi: {dest.stat().st_size / 1024:.2f} KB")

if __name__ == "__main__":
    asyncio.run(run_backup())
