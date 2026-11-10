# 🎬 FlixUz Enterprise Cinema Bot & Admin Mini App
> **Professional Telegram Bot Development — To‘liq Texnik Standartlar (Master Checklist) Asosida Yaratilgan Tizim**

Ushbu loyiha oddiy Telegram bot emas, balki minglab foydalanuvchilarga barqaror xizmat ko‘rsatuvchi, xavfsiz, asinxron, ko‘p tilli va o‘zining zamonaviy **Admin Mini App (Web Dashboard)** boshqaruv markaziga ega bo‘lgan to‘liq ekotizimdir.

---

## 🏛 1. Tizim Arxitekturasi

Loyiha professional mikro-modulli arxitekturada barpo etilgan:

```text
CineVerse-Bot/
├── bot.py                    # Asosiy ishga tushirish fayli
├── config.py                 # Konfiguratsiyalar va .env integratsiyasi
├── database/
│   ├── cinema.db             # SQLite asinxron bazasi (Postgres-ready)
│   └── db.py                 # 15 ta jadval, indekslar va tranzaksiyalar
├── handlers/
│   ├── start.py              # /start, deep-linking, referal, /menu
│   ├── movies.py             # Filmlar, seriallar, anime, drama, qidiruv
│   ├── premium.py            # Premium va VIP tariflar, obunani tekshirish
│   ├── support.py            # /support ticket tizimi va operator yozishmalari
│   ├── extra.py              # /profile, /settings, /language, /promo, /about, /privacy, /terms
│   ├── admin.py              # /admin, /stats, /monthly, /users, /blockuser
│   ├── media_mgmt.py         # /addmedia, /deletemedia, /medialist, /access
│   └── admin_mgmt.py         # /addadmin (teng huquqli adminlar), /removeadmin
├── keyboards/
│   ├── reply.py              # Asosiy doimiy menyu tugmalari
│   └── inline.py             # Toifalar, pagination va serial qismlari tugmalari
├── locales/
│   └── i18n.py               # Ko'p tillilik (O'zbekcha 🇺🇿, Русский 🇷🇺, English 🇬🇧)
├── middlewares/
│   ├── throttling.py         # Anti-Spam / Anti-Flood (Rate limiting)
│   └── ban_check.py          # Bloklanganlarni nazorat qilish va faollik qaydi
├── webapp/
│   ├── static/index.html     # Dark Glassmorphism Admin Mini App (SPA)
│   ├── auth.py               # Telegram WebApp HMAC SHA-256 xavfsizlik tekshiruvi
│   └── server.py             # REST API server (aiohttp)
├── workers/
│   └── scheduler.py          # Fon vazifalari (Obunalar nazorati, Avto-backup)
├── scripts/
│   └── backup.py             # Qo'lda yoki cron orqali zaxira olish skripti
├── tests/
│   └── test_bot.py           # Avtomatlashtirilgan unit testlar to'plami
├── backups/                  # Avtomatik va qo'lda olingan zaxiralar
├── logs/                     # Tizim va xatoliklar loglari
├── Dockerfile                # Konteynerlash
├── docker-compose.yml        # Docker Compose orqali 1-bosishda ishga tushirish
├── requirements.txt          # Python kutubxonalari
└── .env                      # Xavfsiz muhit sozlamalari
```

---

## ⚡️ 2. Master Checklist Bo‘yicha Bajarilgan Imkoniyatlar:

### 👤 2.1. Foydalanuvchi Interfeysi (UI/UX) va Buyruqlar:
- `/start` — Botni ishga tushirish, do‘stlarni taklif qilganda referal hisoblash (`start=ref_12345`), kino kodini to‘g‘ridan-to‘g‘ri ochish (`start=101`).
- `/menu` — Barcha bo‘limlar jamlangan bosh menyu.
- `/movies` — Filmlar, Seriallar, Anime va Dramalar katalogi (sahifalash bilan).
- `/profile` — Foydalanuvchi kartochkasi: ID, Ism, Status, Ballar, Referal soni va shaxsiy referal havola.
- `/premium` — Obuna tariflari (1 oy, 3 oy, 1 yil, VIP).
- `/promo` — Chegirma yoki bepul Premium beruvchi promokodlarni kiritish.
- `/support` — Texnik yordam markaziga murojaat yuborish (Ticket ID generatsiyasi).
- `/settings` — Sozlamalar va bildirishnomalar.
- `/language` — Bot tilini bir zumda almashtirish (🇺🇿 O‘zbekcha, 🇷🇺 Русский, 🇬🇧 English).
- `/about` — Bot haqida ma'lumot va versiya.
- `/privacy` — Maxfiylik siyosati (Privacy Policy).
- `/terms` — Foydalanish shartlari (Terms of Service).

### 👥 2.2. Foydalanuvchilarni Boshqarish va Referal Tizimi:
- Har bir foydalanuvchi uchun unikal referal havola: `https://t.me/FlixUzCinemaBot?start=ref_USERID`.
- Taklif qilingan har bir do‘st uchun 10 ball beriladi.
- O‘zini o‘zi taklif qilishdan himoya (Anti-fraud).
- Foydalanuvchilarni qidirish, bloklash va blokdan chiqarish.

### 🛡 2.3. Xavfsizlik Tizimi (Security):
- **Token himoyasi:** Barcha sirlar `.env` faylida saqlanadi.
- **Throttling (Rate Limiting):** Foydalanuvchilar soniyasiga me'yoridan ortiq xabar yuborsa, tizim avtomatik bloklaydi va botni Telegram API limitlaridan asraydi.
- **HMAC SHA-256 WebApp Auth:** Admin Mini App faqat rasmiy Telegram orqali ochilganini tekshiradi va begona shaxslarni kiritmaydi.
- **RBAC (Role-Based Access Control):** `super_admin`, `admin`, `moderator`, `operator` rollari.

### 👑 2.4. Teng Huquqli Adminlar Tizimi:
- Bosh admin boshqa foydalanuvchini **siz bilan teng huquqli admin** etib tayinlashi mumkin:
  - Foydalanuvchining xabarini Forward qilish orqali.
  - `@username` yozish orqali.
  - Telegram ID yozish orqali.
  - Mini Appning "Userlar" bo‘limida bitta tugma orqali.
- Yangi admin ham to‘liq boshqaruvga, Mini Appga va barcha imtiyozlarga ega bo‘ladi.

### 🎟 2.5. Yordam Markazi (Support Tickets):
- Foydalanuvchi `/support` orqali muammosini yozadi.
- Tizim unga `TICKET-YYMMDD-XXX` raqamini biriktiradi.
- Barcha adminlarga bildirishnoma boradi va ular to‘g‘ridan-to‘g‘ri botdan yoki Mini Appdan javob yo‘llashlari mumkin.

### ⚙️ 2.6. Background Worker & Avtomatik Zaxira (Scheduler):
- **Obuna nazorati:** Har kuni obunasi tugaganlarni avtomatik aniqlab Premium maqomini to‘xtatadi va foydalanuvchini ogohlantiradi (3 kun oldin va muddati tugagan kuni).
- **Avtomatik Backup:** Har kuni ma'lumotlar bazasini `backups/` jildiga zaxiralab boradi.

### 📦 2.7. Ommaviy Qismlarni Yuklash (Batch Upload & Anti-Flood):
- **100 tagacha qismni bir tashlashda yuklash:** Telegram galereyasidan bir vaqtda 15, 20, 50, 100 ta videoni tanlab jo‘natganda poyga holatisiz (`asyncio.Lock`) qabul qilish.
- **Smart Regex:** Qism raqamini video izohi yoki nomidan avtomatik aniqlash (`15-qism`, `ep 15`, `S01E15`, `15-серия`).
- **Debounced Live Progress:** 100 ta alohida xabar yuborib spam qilmaydi; bitta status xabarini soniyasiga 1 marta yangilab, Telegram FloodWait (429) dan himoya qiladi.
- **File ID lar ro‘yxati (Bulk Paste):** Barcha Telegram File ID larni bir vaqtda matn ko‘rinishida tashlab bazaga saqlash.
- **Admin Mini App:** Brauzerdagi WebApp orqali ham barcha qismlarni bir zumda ommaviy kiritish.

---

## 🚀 3. Ishga Tushirish

### Mahalliy muhitda (Local):
```powershell
cd "c:\Users\user\Desktop\CineVerse-Bot"
py bot.py
```

### Docker orqali (Production):
```bash
docker-compose up -d --build
```

### Avtomatlashtirilgan testlarni tekshirish:
```powershell
py -m unittest tests/test_bot.py
```

### Qo‘lda ma'lumotlar bazasini zaxiralash:
```powershell
py scripts/backup.py
```
