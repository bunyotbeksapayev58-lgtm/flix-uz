import json
import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import aiosqlite

from config import DB_PATH, SUPER_ADMIN_ID

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path=DB_PATH):
        self.db_path = str(db_path)

    async def init_db(self):
        """Barcha 15 ta jadval va indekslarni yaratish (Master Checklist talablari asosida)"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA foreign_keys = ON;")
            await db.execute("PRAGMA journal_mode = WAL;")
            await db.execute("PRAGMA busy_timeout = 5000;")

            # 1. USERS (Foydalanuvchilar)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    language TEXT DEFAULT 'uz',
                    role TEXT DEFAULT 'user', -- 'user', 'operator', 'moderator', 'admin', 'super_admin'
                    is_blocked INTEGER DEFAULT 0,
                    is_premium INTEGER DEFAULT 0,
                    premium_until TEXT,
                    reminder_sent INTEGER DEFAULT 0,
                    subscription_tier TEXT DEFAULT 'free', -- 'free', 'premium', 'vip'
                    referrer_id INTEGER,
                    referral_count INTEGER DEFAULT 0,
                    points INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_active_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Migratsiya: mavjud users jadvaliga yangi ustunlarni qo'shish
            async with db.execute("PRAGMA table_info(users)") as cur:
                columns = [row[1] for row in await cur.fetchall()]
            
            user_migrations = [
                ("role", "TEXT DEFAULT 'user'"),
                ("language", "TEXT DEFAULT 'uz'"),
                ("last_name", "TEXT"),
                ("joined_at", "TEXT DEFAULT CURRENT_TIMESTAMP"),
                ("is_premium", "INTEGER DEFAULT 0"),
                ("premium_until", "TEXT"),
                ("reminder_sent", "INTEGER DEFAULT 0"),
                ("subscription_tier", "TEXT DEFAULT 'free'"),
                ("referrer_id", "INTEGER"),
                ("referral_count", "INTEGER DEFAULT 0"),
                ("points", "INTEGER DEFAULT 0")
            ]
            for col_name, col_type in user_migrations:
                if col_name not in columns:
                    await db.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")

            # 2. ROLES & PERMISSIONS (RBAC)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS roles_permissions (
                    role TEXT PRIMARY KEY,
                    permissions TEXT -- JSON array: ["manage_media", "manage_users", "view_analytics", "broadcast", "manage_tickets", "manage_admins", "manage_finances"]
                )
            """)

            # Boshlang'ich rollarni kiritish
            default_roles = [
                ("super_admin", json.dumps(["manage_media", "manage_users", "view_analytics", "broadcast", "manage_tickets", "manage_admins", "manage_finances", "system_settings"])),
                ("admin", json.dumps(["manage_media", "manage_users", "view_analytics", "broadcast", "manage_tickets", "manage_admins"])),
                ("moderator", json.dumps(["manage_media", "manage_users", "view_analytics", "manage_tickets"])),
                ("operator", json.dumps(["manage_tickets", "view_analytics"]))
            ]
            for role_name, perms in default_roles:
                await db.execute(
                    "INSERT OR IGNORE INTO roles_permissions (role, permissions) VALUES (?, ?)",
                    (role_name, perms)
                )

            # 3. ADMINS (Administratorlar)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    role TEXT DEFAULT 'admin',
                    added_by INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            async with db.execute("PRAGMA table_info(admins)") as cur:
                admin_columns = [row[1] for row in await cur.fetchall()]
            if "role" not in admin_columns:
                await db.execute("ALTER TABLE admins ADD COLUMN role TEXT DEFAULT 'admin'")
            if "added_by" not in admin_columns:
                await db.execute("ALTER TABLE admins ADD COLUMN added_by INTEGER DEFAULT 0")

            # 4. USER SETTINGS (Foydalanuvchi sozlamalari)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    notifications_enabled INTEGER DEFAULT 1,
                    language TEXT DEFAULT 'uz',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

            # 5. SUBSCRIPTIONS (Obunalar)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    plan_name TEXT NOT NULL, -- '1_month', '3_months', '1_year', 'vip'
                    price TEXT NOT NULL,
                    status TEXT DEFAULT 'active', -- 'active', 'expired', 'cancelled'
                    starts_at TEXT,
                    expires_at TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)

            # 6. PAYMENTS (To'lovlar va Tranzaksiyalar)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount TEXT NOT NULL,
                    currency TEXT DEFAULT 'UZS',
                    provider TEXT DEFAULT 'manual', -- 'Telegram Stars', 'Click', 'Payme', 'Manual'
                    status TEXT DEFAULT 'pending', -- 'pending', 'completed', 'refunded', 'failed'
                    transaction_id TEXT UNIQUE,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 7. PROMO CODES (Promokodlar)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS promo_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    days_bonus INTEGER DEFAULT 30,
                    discount_percent INTEGER DEFAULT 0,
                    max_uses INTEGER DEFAULT 100,
                    used_count INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 7.1 PROMO REDEMPTIONS (Promokodni ishlatgan foydalanuvchilar)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS promo_redemptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    promo_code TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    redeemed_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(promo_code, user_id)
                )
            """)

            # 8. SUPPORT TICKETS (Yordam markazi murojaatlari)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_number TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    subject TEXT NOT NULL,
                    status TEXT DEFAULT 'open', -- 'open', 'in_progress', 'resolved', 'closed'
                    assigned_to INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 9. TICKET MESSAGES (Murojaat yozishmalari)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ticket_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id INTEGER NOT NULL,
                    sender_id INTEGER NOT NULL,
                    is_from_admin INTEGER DEFAULT 0,
                    text TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(ticket_id) REFERENCES support_tickets(id) ON DELETE CASCADE
                )
            """)

            # 10. BROADCASTS (Ommaviy xabarlar hisoboti)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS broadcasts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    author_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    target_audience TEXT DEFAULT 'all', -- 'all', 'free', 'premium', 'active_30d'
                    status TEXT DEFAULT 'pending', -- 'pending', 'sending', 'completed', 'failed'
                    total_targets INTEGER DEFAULT 0,
                    sent_count INTEGER DEFAULT 0,
                    failed_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT
                )
            """)

            # 11. ACTIVITY LOGS (Foydalanuvchi va Admin faollik tarixi)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS activity_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT NOT NULL,
                    details TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 12. ERROR LOGS (Texnik xatoliklar jurnali)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS error_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    module TEXT,
                    error_type TEXT,
                    message TEXT,
                    traceback TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 13. SYSTEM SETTINGS (Tizim konfiguratsiyalari)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # 14. MEDIA (Kino, Serial, Anime, Drama, Multfilm)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS media (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    original_title TEXT,
                    poster_file_id TEXT,
                    duration TEXT,
                    language TEXT DEFAULT 'O''zbekcha',
                    age_rating TEXT DEFAULT '12+',
                    genre TEXT,
                    year TEXT,
                    description TEXT,
                    file_id TEXT NOT NULL,
                    file_type TEXT DEFAULT 'video',
                    is_premium INTEGER DEFAULT 0,
                    views_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Media jadvali migratsiyasi
            async with db.execute("PRAGMA table_info(media)") as cur:
                m_columns = [row[1] for row in await cur.fetchall()]

            media_migrations = [
                ("original_title", "TEXT"),
                ("poster_file_id", "TEXT"),
                ("duration", "TEXT"),
                ("language", "TEXT DEFAULT 'O''zbekcha'"),
                ("age_rating", "TEXT DEFAULT '12+'")
            ]
            for col_name, col_type in media_migrations:
                if col_name not in m_columns:
                    await db.execute(f"ALTER TABLE media ADD COLUMN {col_name} {col_type}")

            # 15. EPISODES (Serial va Anime qismlari)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    media_code TEXT NOT NULL,
                    season_num INTEGER DEFAULT 1,
                    episode_num INTEGER NOT NULL,
                    title TEXT,
                    file_id TEXT NOT NULL,
                    file_type TEXT DEFAULT 'video',
                    is_premium INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Episodes jadvali migratsiyasi
            async with db.execute("PRAGMA table_info(episodes)") as cur:
                ep_columns = [row[1] for row in await cur.fetchall()]
            if "is_premium" not in ep_columns:
                await db.execute("ALTER TABLE episodes ADD COLUMN is_premium INTEGER DEFAULT 0")
            if "file_type" not in ep_columns:
                await db.execute("ALTER TABLE episodes ADD COLUMN file_type TEXT DEFAULT 'video'")

            # 16. FAVORITES (Sevimlilar)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS favorites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    media_code TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, media_code)
                )
            """)

            # 17. WATCH HISTORY (Ko'rishlar tarixi)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS watch_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    media_code TEXT NOT NULL,
                    watched_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 18. REQUIRED CHANNELS (Majburiy obuna kanallari)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS required_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id TEXT NOT NULL UNIQUE,
                    channel_name TEXT,
                    invite_link TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 19. MOVIE REQUESTS (Foydalanuvchilar kino so'rovlari)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS movie_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    movie_title TEXT NOT NULL,
                    status TEXT DEFAULT 'pending', -- 'pending', 'fulfilled', 'rejected'
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # INDEKSLAR (Tezkor qidiruv va yuklama optimizatsiyasi)
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
                "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)",
                "CREATE INDEX IF NOT EXISTS idx_media_code ON media(code)",
                "CREATE INDEX IF NOT EXISTS idx_media_category ON media(category)",
                "CREATE INDEX IF NOT EXISTS idx_episodes_code ON episodes(media_code)",
                "CREATE INDEX IF NOT EXISTS idx_req_channels ON required_channels(channel_id)",
                "CREATE INDEX IF NOT EXISTS idx_requests_user ON movie_requests(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_requests_status ON movie_requests(status)",
                "CREATE INDEX IF NOT EXISTS idx_tickets_user ON support_tickets(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_promo_redemptions_user ON promo_redemptions(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_activity_logs_user ON activity_logs(user_id)"
            ]
            for idx_query in indexes:
                await db.execute(idx_query)

            # Super adminni tekshirish va ro'yxatga olish
            if SUPER_ADMIN_ID:
                await db.execute(
                    "INSERT OR IGNORE INTO admins (user_id, role, added_by) VALUES (?, 'super_admin', 0)",
                    (SUPER_ADMIN_ID,)
                )
                await db.execute("""
                    INSERT INTO users (id, first_name, role)
                    VALUES (?, 'Super Admin', 'super_admin')
                    ON CONFLICT(id) DO UPDATE SET role = 'super_admin'
                """, (SUPER_ADMIN_ID,))

            await db.commit()
            logger.info("✅ Professional ma'lumotlar bazasi jadvallari va indekslari tayyorlandi.")

    # ==================== FOYDALANUVCHILAR BOSHQARUVI ====================

    async def add_or_update_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        referrer_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Foydalanuvchini ro'yxatga olish yoki oxirgi faolligini yangilash"""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cur:
                existing = await cur.fetchone()

            if not existing:
                # Yangi foydalanuvchi
                valid_ref = None
                if referrer_id and referrer_id != user_id:
                    async with db.execute("SELECT 1 FROM users WHERE id = ?", (referrer_id,)) as rcur:
                        if await rcur.fetchone():
                            valid_ref = referrer_id
                            # Taklif qilgan foydalanuvchiga ball va referal hisobini oshirish
                            await db.execute("""
                                UPDATE users SET
                                    referral_count = referral_count + 1,
                                    points = points + 10
                                WHERE id = ?
                            """, (referrer_id,))

                            # Referal rag'batlantirish: 3 ta -> 3 kun, 10 ta -> 15 kun, 25 ta -> 30 kun Premium
                            async with db.execute("SELECT referral_count FROM users WHERE id = ?", (referrer_id,)) as rcnt_cur:
                                r_row = await rcnt_cur.fetchone()
                                r_cnt = r_row[0] if r_row else 0

                            bonus_days = 0
                            if r_cnt == 3:
                                bonus_days = 3
                            elif r_cnt == 10:
                                bonus_days = 15
                            elif r_cnt == 25:
                                bonus_days = 30

                            if bonus_days > 0:
                                now_dt = datetime.now(timezone.utc)
                                bonus_expires = (now_dt + timedelta(days=bonus_days)).strftime("%Y-%m-%d %H:%M:%S")
                                await db.execute("""
                                    UPDATE users 
                                    SET is_premium = 1, premium_until = ?, subscription_tier = 'referral_bonus'
                                    WHERE id = ?
                                """, (bonus_expires, referrer_id))

                await db.execute("""
                    INSERT INTO users (id, username, first_name, last_name, referrer_id, joined_at, last_active_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user_id, username, first_name, last_name, valid_ref, now, now))
                await db.commit()

                # Sozlamalar jadvalini yaratish
                await db.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user_id,))
                await db.commit()

                # Activity log
                await self.log_activity(user_id, "register", f"Yangi ro'yxatdan o'tdi (Ref: {valid_ref})")
            else:
                # Oxirgi faollikni yangilash
                await db.execute("""
                    UPDATE users SET
                        username = COALESCE(?, username),
                        first_name = COALESCE(?, first_name),
                        last_name = COALESCE(?, last_name),
                        last_active_at = ?
                    WHERE id = ?
                """, (username, first_name, last_name, now, user_id))
                await db.commit()

        return await self.get_user(user_id)

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        clean_un = username.lstrip("@").strip().lower()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE LOWER(username) = ?", (clean_un,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def set_user_language(self, user_id: int, lang: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET language = ? WHERE id = ?", (lang, user_id))
            await db.execute("UPDATE user_settings SET language = ? WHERE user_id = ?", (lang, user_id))
            await db.commit()

    async def get_user_language(self, user_id: int) -> str:
        u = await self.get_user(user_id)
        return u["language"] if u and u.get("language") else "uz"

    async def is_user_blocked(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT is_blocked FROM users WHERE id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return bool(row[0]) if row else False

    async def block_user(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("UPDATE users SET is_blocked = 1 WHERE id = ?", (user_id,))
            await db.commit()
            await self.log_activity(user_id, "block", "Foydalanuvchi bloklandi")
            return cur.rowcount > 0

    async def unblock_user(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("UPDATE users SET is_blocked = 0 WHERE id = ?", (user_id,))
            await db.commit()
            await self.log_activity(user_id, "unblock", "Foydalanuvchi blokdan chiqarildi")
            return cur.rowcount > 0

    # ==================== PREMIUM & SUBSCRIPTIONS ====================

    async def is_user_premium(self, user_id: int) -> bool:
        """Foydalanuvchi premium huquqiga egami (Adminlar avtomatik premium)"""
        if await self.is_admin(user_id):
            return True
        user = await self.get_user(user_id)
        if not user or not user["is_premium"]:
            return False
        if not user.get("premium_until"):
            return True
        try:
            exp_date = datetime.strptime(user["premium_until"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if exp_date > datetime.now(timezone.utc):
                return True
            else:
                await self.remove_user_premium(user_id)
                return False
        except Exception:
            return bool(user["is_premium"])

    async def set_user_premium(self, user_id: int, days: int = 30, tier: str = "premium") -> bool:
        now_dt = datetime.now(timezone.utc)
        base_dt = now_dt
        user = await self.get_user(user_id)
        if user and user.get("premium_until"):
            try:
                current_until = datetime.strptime(user["premium_until"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if current_until > now_dt:
                    base_dt = current_until
            except Exception:
                pass
        expires = (base_dt + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("""
                UPDATE users 
                SET is_premium = 1, premium_until = ?, subscription_tier = ?, reminder_sent = 0
                WHERE id = ?
            """, (expires, tier, user_id))
            # Subscriptions jadvaliga qayd kiritish
            await db.execute("""
                INSERT INTO subscriptions (user_id, plan_name, price, status, starts_at, expires_at)
                VALUES (?, ?, ?, 'active', ?, ?)
            """, (user_id, f"{days}_days", "VIP" if tier == "vip" else "Standard", now_dt.strftime("%Y-%m-%d %H:%M:%S"), expires))
            await db.commit()
            await self.log_activity(user_id, "grant_premium", f"{days} kunlik {tier} berildi (Muddati: {expires})")
            return cur.rowcount > 0

    async def remove_user_premium(self, user_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("""
                UPDATE users 
                SET is_premium = 0, premium_until = NULL, subscription_tier = 'free', reminder_sent = 0
                WHERE id = ?
            """, (user_id,))
            await db.commit()
            return cur.rowcount > 0

    async def redeem_promo_code(self, user_id: int, code_str: str) -> Dict[str, Any]:
        """Promokodni tekshirish va ishlatish (Atomik va bir martalik)"""
        code_str = code_str.strip().upper()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 1. Foydalanuvchi bu promokodni oldin ishlatganligini tekshirish
            async with db.execute(
                "SELECT 1 FROM promo_redemptions WHERE promo_code = ? AND user_id = ?",
                (code_str, user_id)
            ) as rcur:
                if await rcur.fetchone():
                    return {"ok": False, "message": "Siz ushbu promokoddan allaqachon foydalangansiz!"}

            # 2. Promokod mavjudligini tekshirish
            async with db.execute("SELECT * FROM promo_codes WHERE code = ? AND is_active = 1", (code_str,)) as cur:
                promo = await cur.fetchone()

            if not promo:
                return {"ok": False, "message": "Bunday promokod mavjud emas yoki muddati o'tgan!"}

            days = promo["days_bonus"]

            # 3. Atomik ravishda limitni tekshirish va ishlatish hisobini oshirish
            cur = await db.execute("""
                UPDATE promo_codes 
                SET used_count = used_count + 1 
                WHERE id = ? AND used_count < max_uses AND is_active = 1
            """, (promo["id"],))

            if cur.rowcount == 0:
                return {"ok": False, "message": "Ushbu promokoddan foydalanish limiti tugagan!"}

            # 4. Foydalanuvchini promo_redemptions jadvaliga qayd etish
            await db.execute(
                "INSERT INTO promo_redemptions (promo_code, user_id) VALUES (?, ?)",
                (code_str, user_id)
            )
            await db.commit()

        # 5. Foydalanuvchiga bonus kunlarini berish (mavjud muddatga qo'shiladi)
        await self.set_user_premium(user_id, days=days)

        return {"ok": True, "days": days, "message": f"Tabriklaymiz! Sizga {days} kunlik Premium taqdim etildi!"}

    # ==================== RBAC & ADMINLAR BOSHQARUVI ====================

    async def get_admin_count(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM admins") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_super_admin_id(self) -> Optional[int]:
        if SUPER_ADMIN_ID and SUPER_ADMIN_ID > 0:
            return SUPER_ADMIN_ID
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id FROM admins WHERE role = 'super_admin' ORDER BY created_at ASC LIMIT 1") as cursor:
                row = await cursor.fetchone()
                if row:
                    return row[0]
            async with db.execute("SELECT user_id FROM admins ORDER BY created_at ASC LIMIT 1") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def is_super_admin(self, user_id: int) -> bool:
        super_id = await self.get_super_admin_id()
        return super_id == user_id

    async def is_admin(self, user_id: int) -> bool:
        if SUPER_ADMIN_ID and user_id == SUPER_ADMIN_ID:
            return True
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT 1 FROM admins WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return bool(row)

    async def get_user_role(self, user_id: int) -> str:
        u = await self.get_user(user_id)
        return u["role"] if u and u.get("role") else "user"

    async def add_admin(self, user_id: int, role: str = "admin", added_by: int = 0) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    "INSERT INTO admins (user_id, role, added_by) VALUES (?, ?, ?)",
                    (user_id, role, added_by)
                )
                await db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
                await db.commit()
                await self.log_activity(added_by, "add_admin", f"Yangi admin tayinlandi: {user_id} (Rol: {role})")
                return True
            except aiosqlite.IntegrityError:
                return False

    async def remove_admin(self, user_id: int) -> bool:
        super_id = await self.get_super_admin_id()
        if user_id == super_id:
            return False
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
            await db.execute("UPDATE users SET role = 'user' WHERE id = ?", (user_id,))
            await db.commit()
            return cur.rowcount > 0

    async def get_all_admins(self) -> List[int]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id FROM admins") as cursor:
                rows = await cursor.fetchall()
                admins = [r[0] for r in rows]
                if SUPER_ADMIN_ID and SUPER_ADMIN_ID not in admins:
                    admins.append(SUPER_ADMIN_ID)
                return admins

    # ==================== SUPPORT TICKETS ====================

    async def create_support_ticket(self, user_id: int, subject: str, initial_message: str) -> Dict[str, Any]:
        rnd_suffix = random.randint(1000, 9999)
        ticket_number = f"TICKET-{datetime.now(timezone.utc).strftime('%y%m%d%H%M%S')}-{rnd_suffix}"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("""
                INSERT INTO support_tickets (ticket_number, user_id, subject, status, created_at, updated_at)
                VALUES (?, ?, ?, 'open', ?, ?)
            """, (ticket_number, user_id, subject, now, now))
            ticket_id = cur.lastrowid

            await db.execute("""
                INSERT INTO ticket_messages (ticket_id, sender_id, is_from_admin, text, created_at)
                VALUES (?, ?, 0, ?, ?)
            """, (ticket_id, user_id, initial_message, now))
            await db.commit()

            await self.log_activity(user_id, "ticket_create", f"Murojaat ochildi: #{ticket_number}")
            return {"id": ticket_id, "ticket_number": ticket_number}

    async def add_ticket_message(self, ticket_id: int, sender_id: int, text: str, is_from_admin: bool = False) -> bool:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO ticket_messages (ticket_id, sender_id, is_from_admin, text, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (ticket_id, sender_id, 1 if is_from_admin else 0, text, now))
            await db.execute("UPDATE support_tickets SET updated_at = ? WHERE id = ?", (now, ticket_id))
            await db.commit()
            return True

    async def get_user_tickets(self, user_id: int) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM support_tickets WHERE user_id = ? ORDER BY id DESC", (user_id,)) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def get_all_tickets(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if status:
                async with db.execute("SELECT * FROM support_tickets WHERE status = ? ORDER BY updated_at DESC", (status,)) as cur:
                    rows = await cur.fetchall()
                    return [dict(r) for r in rows]
            else:
                async with db.execute("SELECT * FROM support_tickets ORDER BY updated_at DESC", ()) as cur:
                    rows = await cur.fetchall()
                    return [dict(r) for r in rows]

    # ==================== MEDIA VA QISMLAR ====================

    async def generate_unique_code(self) -> str:
        """Avtomatik 5 xonali noyob film kodi generatsiya qilish (masalan: 12345)"""
        import random
        for _ in range(50):
            candidate = str(random.randint(10000, 99999))
            existing = await self.get_media_by_code(candidate)
            if not existing:
                return candidate
        # Agar tasodifiy tugasa, timestamp asosida
        return str(int(datetime.now(timezone.utc).timestamp()) % 100000)

    async def add_media(
        self,
        code: str,
        category: str,
        title: str,
        genre: str = "",
        year: str = "",
        description: str = "",
        file_id: str = "",
        file_type: str = "video",
        is_premium: int = 0,
        original_title: str = "",
        poster_file_id: str = "",
        duration: str = "",
        language: str = "O'zbekcha",
        age_rating: str = "12+"
    ) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("""
                    INSERT INTO media (
                        code, category, title, original_title, poster_file_id, duration,
                        language, age_rating, genre, year, description, file_id, file_type, is_premium
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    code.strip(), category.lower().strip(), title.strip(),
                    original_title.strip() if original_title else "",
                    poster_file_id.strip() if poster_file_id else "",
                    duration.strip() if duration else "",
                    language.strip() if language else "O'zbekcha",
                    age_rating.strip() if age_rating else "12+",
                    genre.strip() if genre else "", str(year).strip() if year else "",
                    description.strip() if description else "", file_id.strip(),
                    file_type, int(is_premium)
                ))
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def get_media_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM media WHERE LOWER(code) = LOWER(?)", (code.strip(),)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def search_media(self, query: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Nom, original nom, kod yoki janr bo'yicha qidiruv"""
        q = f"%{query.strip().lower()}%"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM media 
                WHERE LOWER(code) LIKE ? 
                   OR LOWER(title) LIKE ? 
                   OR LOWER(original_title) LIKE ?
                   OR LOWER(genre) LIKE ?
                ORDER BY views_count DESC, id DESC LIMIT ?
            """, (q, q, q, q, limit)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_popular_media(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Eng mashhur filmlar (ko'rishlar soni bo'yicha)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM media ORDER BY views_count DESC LIMIT ?", (limit,)) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def get_recent_media(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Yangi qo'shilgan filmlar"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM media ORDER BY id DESC LIMIT ?", (limit,)) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def get_random_media(self) -> Optional[Dict[str, Any]]:
        """Tasodifiy film"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM media ORDER BY RANDOM() LIMIT 1") as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    # ==================== SEVIMLILAR VA TOMOSHA TARIXI ====================

    async def add_favorite(self, user_id: int, media_code: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    "INSERT OR IGNORE INTO favorites (user_id, media_code) VALUES (?, ?)",
                    (user_id, media_code.strip())
                )
                await db.commit()
                return True
            except Exception:
                return False

    async def remove_favorite(self, user_id: int, media_code: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "DELETE FROM favorites WHERE user_id = ? AND LOWER(media_code) = LOWER(?)",
                (user_id, media_code.strip())
            )
            await db.commit()
            return cur.rowcount > 0

    async def is_favorite(self, user_id: int, media_code: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT 1 FROM favorites WHERE user_id = ? AND LOWER(media_code) = LOWER(?)",
                (user_id, media_code.strip())
            ) as cur:
                row = await cur.fetchone()
                return bool(row)

    async def get_user_favorites(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT m.* FROM media m
                INNER JOIN favorites f ON LOWER(f.media_code) = LOWER(m.code)
                WHERE f.user_id = ?
                ORDER BY f.id DESC LIMIT ?
            """, (user_id, limit)) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def record_watch_history(self, user_id: int, media_code: str):
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO watch_history (user_id, media_code, watched_at)
                VALUES (?, ?, ?)
            """, (user_id, media_code.strip(), now))
            await db.commit()

    async def get_user_history(self, user_id: int, limit: int = 15) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT m.*, w.watched_at FROM media m
                INNER JOIN watch_history w ON LOWER(w.media_code) = LOWER(m.code)
                WHERE w.user_id = ?
                ORDER BY w.id DESC LIMIT ?
            """, (user_id, limit)) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def get_next_episode(self, media_code: str, current_ep: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM episodes 
                WHERE LOWER(media_code) = LOWER(?) AND episode_num > ?
                ORDER BY episode_num ASC LIMIT 1
            """, (media_code.strip(), current_ep)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_prev_episode(self, media_code: str, current_ep: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM episodes 
                WHERE LOWER(media_code) = LOWER(?) AND episode_num < ?
                ORDER BY episode_num DESC LIMIT 1
            """, (media_code.strip(), current_ep)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_media_by_category(self, category: str, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM media 
                WHERE LOWER(category) = LOWER(?)
                ORDER BY id DESC LIMIT ? OFFSET ?
            """, (category.strip(), limit, offset)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def count_media_by_category(self, category: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM media WHERE LOWER(category) = LOWER(?)",
                (category.strip(),)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_all_media(self, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM media ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_total_media_count(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM media") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def delete_media(self, code: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("DELETE FROM media WHERE LOWER(code) = LOWER(?)", (code.strip(),))
            await db.execute("DELETE FROM episodes WHERE LOWER(media_code) = LOWER(?)", (code.strip(),))
            await db.commit()
            return cur.rowcount > 0

    async def update_media(self, code: str, title: str, genre: str, year: str, description: str, is_premium: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("""
                UPDATE media SET
                    title = ?, genre = ?, year = ?, description = ?, is_premium = ?
                WHERE LOWER(code) = LOWER(?)
            """, (title.strip(), genre.strip(), str(year).strip(), description.strip(), int(is_premium), code.strip()))
            await db.commit()
            return cur.rowcount > 0

    async def toggle_media_access(self, code: str) -> Optional[int]:
        media = await self.get_media_by_code(code)
        if not media:
            return None
        new_val = 0 if media["is_premium"] else 1
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE media SET is_premium = ? WHERE LOWER(code) = LOWER(?)", (new_val, code.strip()))
            await db.commit()
        return new_val

    async def increment_media_views(self, code: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE media SET views_count = views_count + 1 WHERE LOWER(code) = LOWER(?)", (code.strip(),))
            await db.commit()

    async def add_episode(
        self,
        media_code: str,
        episode_num: int,
        season_num: int = 1,
        title: str = "",
        file_id: str = "",
        is_premium: int = 0,
        file_type: str = "video"
    ) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            # Agar oldin kiritilgan qism bo'lsa yangilaymiz
            async with db.execute(
                "SELECT id FROM episodes WHERE LOWER(media_code) = LOWER(?) AND season_num = ? AND episode_num = ?",
                (media_code.strip(), int(season_num), int(episode_num))
            ) as cur:
                existing = await cur.fetchone()

            if existing:
                await db.execute("""
                    UPDATE episodes 
                    SET file_id = ?, title = ?, is_premium = ?, file_type = ?
                    WHERE id = ?
                """, (file_id.strip(), title.strip(), int(is_premium), file_type.strip(), existing[0]))
            else:
                await db.execute("""
                    INSERT INTO episodes (media_code, season_num, episode_num, title, file_id, file_type, is_premium)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (media_code.strip(), int(season_num), int(episode_num), title.strip(), file_id.strip(), file_type.strip(), int(is_premium)))
            await db.commit()
            return True

    async def add_episodes_batch(
        self,
        media_code: str,
        episodes: list[dict]
    ) -> int:
        """
        Bir nechta qismlarni bitta tranzaksiyada tezkor saqlash.
        episodes = [
            {"episode_num": 1, "title": "1-qism", "file_id": "...", "file_type": "video", "is_premium": 0},
            ...
        ]
        """
        if not episodes:
            return 0

        added = 0
        async with aiosqlite.connect(self.db_path) as db:
            for ep in episodes:
                ep_num = int(ep.get("episode_num", 1))
                season_num = int(ep.get("season_num", 1))
                title = ep.get("title") or f"{ep_num}-qism"
                file_id = str(ep.get("file_id", "")).strip()
                file_type = str(ep.get("file_type", "video")).strip()
                is_premium = int(ep.get("is_premium", 0))

                if not file_id:
                    continue

                async with db.execute(
                    "SELECT id FROM episodes WHERE LOWER(media_code) = LOWER(?) AND season_num = ? AND episode_num = ?",
                    (media_code.strip(), season_num, ep_num)
                ) as cur:
                    existing = await cur.fetchone()

                if existing:
                    await db.execute("""
                        UPDATE episodes 
                        SET file_id = ?, title = ?, is_premium = ?, file_type = ?
                        WHERE id = ?
                    """, (file_id, title, is_premium, file_type, existing[0]))
                else:
                    await db.execute("""
                        INSERT INTO episodes (media_code, season_num, episode_num, title, file_id, file_type, is_premium)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (media_code.strip(), season_num, ep_num, title, file_id, file_type, is_premium))
                added += 1

            await db.commit()
        return added

    async def set_episodes_access_threshold(self, media_code: str, free_up_to_episode: int) -> bool:
        """
        Masalan: free_up_to_episode = 25 bo'lsa,
        1-25 qismlar bepul (is_premium = 0),
        26-qismdan boshlab barcha qismlar pullik (is_premium = 1) bo'ladi.
        Agar 0 bo'lsa, barchasi bepul bo'ladi.
        """
        async with aiosqlite.connect(self.db_path) as db:
            if free_up_to_episode <= 0:
                await db.execute(
                    "UPDATE episodes SET is_premium = 0 WHERE LOWER(media_code) = LOWER(?)",
                    (media_code.strip(),)
                )
            else:
                await db.execute("""
                    UPDATE episodes 
                    SET is_premium = CASE WHEN episode_num <= ? THEN 0 ELSE 1 END
                    WHERE LOWER(media_code) = LOWER(?)
                """, (int(free_up_to_episode), media_code.strip()))
            await db.commit()
            return True

    # ==================== MAJBURIY OBUNA KANALLARI ====================

    async def add_required_channel(self, channel_id: str, channel_name: str = "", invite_link: str = "") -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("""
                    INSERT INTO required_channels (channel_id, channel_name, invite_link)
                    VALUES (?, ?, ?)
                """, (channel_id.strip(), channel_name.strip(), invite_link.strip()))
                await db.commit()
                return True
            except Exception:
                return False

    async def remove_required_channel(self, channel_identifier: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("""
                DELETE FROM required_channels 
                WHERE LOWER(channel_id) = LOWER(?) OR CAST(id AS TEXT) = ?
            """, (channel_identifier.strip(), channel_identifier.strip()))
            await db.commit()
            return cur.rowcount > 0

    async def get_required_channels(self) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM required_channels ORDER BY id ASC") as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def get_episodes(self, media_code: str) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT * FROM episodes 
                WHERE LOWER(media_code) = LOWER(?)
                ORDER BY season_num ASC, episode_num ASC
            """, (media_code.strip(),)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def delete_episode(self, episode_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("DELETE FROM episodes WHERE id = ?", (episode_id,))
            await db.commit()
            return cur.rowcount > 0

    # ==================== LOGGING & AUDIT ====================

    async def log_activity(self, user_id: int, action: str, details: str = ""):
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO activity_logs (user_id, action, details)
                    VALUES (?, ?, ?)
                """, (user_id, action, details))
                await db.commit()
        except Exception as e:
            logger.error(f"Activity log error: {e}")

    async def log_error(self, module: str, error_type: str, message: str, traceback_str: str = ""):
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO error_logs (module, error_type, message, traceback)
                    VALUES (?, ?, ?, ?)
                """, (module, error_type, message, traceback_str))
                await db.commit()
        except Exception as e:
            logger.error(f"Error log logging failed: {e}")

    # ==================== STATISTIKA & ANALYTICS ====================

    async def get_total_users_count(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_monthly_users_count(self) -> int:
        month_ago = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE last_active_at >= ? OR joined_at >= ?",
                (month_ago, month_ago)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_daily_active_users(self) -> int:
        day_ago = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users WHERE last_active_at >= ?", (day_ago,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0

    async def get_users_list(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users ORDER BY joined_at DESC LIMIT ? OFFSET ?", (limit, offset)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_users_filtered(self, search: str = "", limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if search:
                q = f"%{search.strip().lower()}%"
                async with db.execute("""
                    SELECT * FROM users
                    WHERE LOWER(username) LIKE ? OR LOWER(first_name) LIKE ? OR CAST(id AS TEXT) LIKE ?
                    ORDER BY joined_at DESC LIMIT ? OFFSET ?
                """, (q, q, q, limit, offset)) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(r) for r in rows]
            else:
                return await self.get_users_list(limit=limit, offset=offset)

    async def get_all_user_ids(self) -> List[int]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT id FROM users WHERE is_blocked = 0") as cursor:
                rows = await cursor.fetchall()
                return [r[0] for r in rows]

    async def get_overall_stats(self) -> Dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as cur:
                total_users = (await cur.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1") as cur:
                premium_users = (await cur.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1") as cur:
                blocked_users = (await cur.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM media") as cur:
                total_media = (await cur.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM media WHERE is_premium = 0") as cur:
                free_media = (await cur.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM media WHERE is_premium = 1") as cur:
                premium_media = (await cur.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM media WHERE LOWER(category) = 'kino'") as cur:
                kino_count = (await cur.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM media WHERE LOWER(category) = 'serial'") as cur:
                serial_count = (await cur.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM media WHERE LOWER(category) = 'anime'") as cur:
                anime_count = (await cur.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM media WHERE LOWER(category) = 'drama'") as cur:
                drama_count = (await cur.fetchone())[0]

            async with db.execute("SELECT SUM(views_count) FROM media") as cur:
                row = await cur.fetchone()
                total_views = row[0] if row and row[0] else 0

            dau = await self.get_daily_active_users()
            mau = await self.get_monthly_users_count()

            return {
                "total_users": total_users,
                "dau": dau,
                "mau": mau,
                "premium_users": premium_users,
                "blocked_users": blocked_users,
                "total_media": total_media,
                "free_media": free_media,
                "premium_media": premium_media,
                "kino_count": kino_count,
                "serial_count": serial_count,
                "anime_count": anime_count,
                "drama_count": drama_count,
                "total_views": total_views,
            }

    # ==================== TIZIM SOZLAMALARI ====================

    async def get_setting(self, key: str, default: str = "") -> str:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT value FROM system_settings WHERE key = ?", (key,)) as cur:
                row = await cur.fetchone()
                return row[0] if row else default

    async def set_setting(self, key: str, value: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO system_settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = ?
            """, (key, value, value))
            await db.commit()
            return True

    # ==================== KINO BUYURTMA QILISH / SO'ROVLAR ====================

    async def create_movie_request(self, user_id: int, movie_title: str) -> Dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute("""
                INSERT INTO movie_requests (user_id, movie_title, status)
                VALUES (?, ?, 'pending')
            """, (user_id, movie_title.strip()))
            req_id = cur.lastrowid
            await db.commit()
            await self.log_activity(user_id, "movie_request", f"Kino so'raldi: {movie_title}")
            return {"id": req_id, "user_id": user_id, "movie_title": movie_title, "status": "pending"}

    async def get_movie_requests(self, status: str = "pending", limit: int = 30) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if status == "all":
                query = "SELECT r.*, u.first_name, u.username FROM movie_requests r LEFT JOIN users u ON u.id = r.user_id ORDER BY r.id DESC LIMIT ?"
                params = (limit,)
            else:
                query = "SELECT r.*, u.first_name, u.username FROM movie_requests r LEFT JOIN users u ON u.id = r.user_id WHERE r.status = ? ORDER BY r.id DESC LIMIT ?"
                params = (status, limit)

            async with db.execute(query, params) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows]

    async def fulfill_movie_request(self, request_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM movie_requests WHERE id = ?", (request_id,)) as cur:
                req = await cur.fetchone()
                if not req:
                    return None
                req_data = dict(req)

            await db.execute("UPDATE movie_requests SET status = 'fulfilled' WHERE id = ?", (request_id,))
            await db.commit()
            return req_data

    # ==================== TO'LOVLARNI YOZIB BORISH ====================

    async def record_payment(
        self,
        user_id: int,
        amount: str,
        currency: str = "XTR",
        provider: str = "Telegram Stars",
        status: str = "completed",
        transaction_id: str = ""
    ) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO payments (user_id, amount, currency, provider, status, transaction_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, str(amount), currency, provider, status, transaction_id or str(int(datetime.now(timezone.utc).timestamp()))))
            await db.commit()
            await self.log_activity(user_id, "payment_success", f"{amount} {currency} ({provider})")
            return True

db = Database()
