import os
import sys
import unittest
import asyncio
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from database import db
from locales.i18n import get_text
from webapp.auth import validate_init_data

TEST_DB_PATH = BASE_DIR / "database" / "test_cinema.db"

class EnterpriseBotTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        # Alohida test ma'lumotlar bazasini yaratish (Asosiy cinema.db ni bulg'amaslik uchun)
        for p in [TEST_DB_PATH, Path(str(TEST_DB_PATH) + "-wal"), Path(str(TEST_DB_PATH) + "-shm")]:
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass
        db.db_path = str(TEST_DB_PATH)

    @classmethod
    def tearDownClass(cls):
        # Test tugagach vaqtinchalik test bazasini tozalash
        for p in [TEST_DB_PATH, Path(str(TEST_DB_PATH) + "-wal"), Path(str(TEST_DB_PATH) + "-shm")]:
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

    async def asyncSetUp(self):
        await db.init_db()

    async def test_01_user_registration_and_referral(self):
        """Foydalanuvchi ro'yxatdan o'tishi va referal hisoblash"""
        ref_user = await db.add_or_update_user(user_id=111111, username="referrer_user", first_name="Referrer")
        self.assertIsNotNone(ref_user)

        new_user = await db.add_or_update_user(user_id=222222, username="invited_user", first_name="Invited", referrer_id=111111)
        self.assertIsNotNone(new_user)
        self.assertEqual(new_user["referrer_id"], 111111)

        # Taklif qilgan odamning referal soni oshganini tekshirish
        ref_updated = await db.get_user(111111)
        self.assertGreaterEqual(ref_updated["referral_count"], 1)

    async def test_02_promo_code_redemption_and_single_use(self):
        """Promokodni faollashtirish va bir foydalanuvchi faqat 1 marta ishlata olishi"""
        import aiosqlite
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute("INSERT OR IGNORE INTO promo_codes (code, days_bonus, max_uses) VALUES ('TESTPROMO', 15, 10)")
            await conn.commit()

        # Birinchi marta ishlatish - muvaffaqiyatli
        res = await db.redeem_promo_code(user_id=222222, code_str="TESTPROMO")
        self.assertTrue(res["ok"])
        self.assertEqual(res["days"], 15)

        # Foydalanuvchi premium bo'lganini tekshirish
        is_prem = await db.is_user_premium(222222)
        self.assertTrue(is_prem)

        # Ikkinchi marta o'sha user ishlatsa - rad etilishi kerak!
        res2 = await db.redeem_promo_code(user_id=222222, code_str="TESTPROMO")
        self.assertFalse(res2["ok"])
        self.assertIn("allaqachon", res2["message"].lower())

    async def test_02b_premium_duration_stacking(self):
        """Premium muddatini uzaytirish (ustma-ust qo'shilishi)"""
        u = await db.get_user(222222)
        old_until = u.get("premium_until")
        self.assertIsNotNone(old_until)

        # Yana 30 kun qo'shamiz
        await db.set_user_premium(222222, days=30)
        u_new = await db.get_user(222222)
        new_until = u_new.get("premium_until")
        self.assertGreater(new_until, old_until)

    async def test_03_support_ticket_flow(self):
        """Yordam markazi murojaat tizimi"""
        ticket = await db.create_support_ticket(user_id=222222, subject="Kino ochilmadi", initial_message="Salom, 101 kodli kino ochilmadi")
        self.assertIn("ticket_number", ticket)
        self.assertTrue(ticket["ticket_number"].startswith("TICKET-"))

        ok = await db.add_ticket_message(ticket["id"], sender_id=111111, text="Operator javobi: muammo hal qilindi", is_from_admin=True)
        self.assertTrue(ok)

    async def test_04_media_and_episodes(self):
        """Media va qismlar yaratilishi"""
        code = "TEST_SERIAL_99"
        await db.add_media(
            code=code,
            category="serial",
            title="Sinov Seriali",
            genre="Drama",
            year="2026",
            description="Sinov uchun serial",
            file_id="BAACAgIAAxkBAA...",
            is_premium=0
        )

        media = await db.get_media_by_code(code)
        self.assertIsNotNone(media)
        self.assertEqual(media["title"], "Sinov Seriali")

        # Qism qo'shish (file_type bilan)
        ep_ok = await db.add_episode(media_code=code, episode_num=1, title="Birinchi qism", file_id="EP_FILE_1", file_type="video")
        self.assertTrue(ep_ok)

        episodes = await db.get_episodes(code)
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0].get("file_type"), "video")

        # Tozalash
        await db.delete_media(code)
        media_after = await db.get_media_by_code(code)
        self.assertIsNone(media_after)

    def test_05_i18n_locales(self):
        """Ko'p tillilik tizimi (uz, ru, en)"""
        uz_txt = get_text("welcome", "uz", name="Ali")
        self.assertIn("Ali", uz_txt)
        self.assertIn("FlixUz", uz_txt)

        ru_txt = get_text("welcome", "ru", name="Али")
        self.assertIn("Здравствуйте", ru_txt)

        en_txt = get_text("welcome", "en", name="Alex")
        self.assertIn("Welcome", en_txt)

    async def test_06_favorites_and_history(self):
        """Sevimlilar va ko'rishlar tarixi funksionalligi"""
        test_code = "TEST_FAV_01"
        await db.add_media(
            code=test_code,
            category="kino",
            title="Sevimlilar Sinovi",
            file_id="TEST_VID_ID"
        )
        user_id = 999888

        # Sevimlilarga qo'shish
        add_ok = await db.add_favorite(user_id, test_code)
        self.assertTrue(add_ok)

        is_fav = await db.is_favorite(user_id, test_code)
        self.assertTrue(is_fav)

        favs = await db.get_user_favorites(user_id)
        self.assertTrue(any(f["code"] == test_code for f in favs))

        # Tarixga yozish
        await db.record_watch_history(user_id, test_code)
        history = await db.get_user_history(user_id)
        self.assertTrue(any(h["code"] == test_code for h in history))

        # Sevimlilardan o'chirish
        del_ok = await db.remove_favorite(user_id, test_code)
        self.assertTrue(del_ok)
        self.assertFalse(await db.is_favorite(user_id, test_code))

        await db.delete_media(test_code)

    async def test_07_unique_code_and_discovery(self):
        """Noyob kod generatsiyasi va kashf qilish"""
        code = await db.generate_unique_code()
        self.assertTrue(code.isdigit())
        self.assertEqual(len(code), 5)

        media = await db.get_media_by_code(code)
        self.assertIsNone(media)

    async def test_08_episodes_freemium_threshold(self):
        """Serial qismlarini bepul va pullik chegarasini sozlash"""
        code = "ANIME_TEST_FREEMIUM"
        await db.add_media(
            code=code,
            category="anime",
            title="Freemium Anime",
            file_id="VID_TEST"
        )
        # 5 ta qism qo'shamiz
        for ep in range(1, 6):
            await db.add_episode(code, episode_num=ep, file_id=f"EP_FILE_{ep}")

        # 3-qismgacha bepul (1, 2, 3 bepul, 4, 5 premium)
        await db.set_episodes_access_threshold(code, free_up_to_episode=3)

        episodes = await db.get_episodes(code)
        self.assertEqual(len(episodes), 5)
        for ep in episodes:
            if ep["episode_num"] <= 3:
                self.assertEqual(ep["is_premium"], 0)
            else:
                self.assertEqual(ep["is_premium"], 1)

        await db.delete_media(code)

    async def test_09_required_channels_management(self):
        """Majburiy a'zolik kanallari boshqaruvi"""
        ch_test = "@test_cinema_channel"
        ok = await db.add_required_channel(ch_test, channel_name="Test Kanal", invite_link="https://t.me/test_cinema_channel")
        self.assertTrue(ok)

        channels = await db.get_required_channels()
        self.assertTrue(any(c["channel_id"] == ch_test for c in channels))

        # O'chirish
        del_ok = await db.remove_required_channel(ch_test)
        self.assertTrue(del_ok)
        channels_after = await db.get_required_channels()
        self.assertFalse(any(c["channel_id"] == ch_test for c in channels_after))

    async def test_10_movie_request_flow(self):
        """Kino buyurtma qilish va uni bajarish tizimi"""
        req = await db.create_movie_request(user_id=123456, movie_title="Oppenheimer 2023")
        self.assertIsNotNone(req)
        self.assertEqual(req["movie_title"], "Oppenheimer 2023")

        pending = await db.get_movie_requests(status="pending")
        self.assertTrue(any(r["id"] == req["id"] for r in pending))

        fulfilled = await db.fulfill_movie_request(req["id"])
        self.assertIsNotNone(fulfilled)

    async def test_11_settings_and_payment_records(self):
        """Sozlamalar va Telegram Stars to'lovlarini yozish"""
        await db.set_setting("posting_channel", "@test_kino_channel")
        val = await db.get_setting("posting_channel")
        self.assertEqual(val, "@test_kino_channel")

        # To'lovni yozish
        pay_ok = await db.record_payment(
            user_id=123456,
            amount="75",
            currency="XTR",
            provider="Telegram Stars",
            status="completed",
            transaction_id="tx_stars_test_99"
        )
        self.assertTrue(pay_ok)

    def test_12_episode_number_regex_extraction(self):
        """Ommaviy yuklashda qism raqamini izoh va fayl nomidan aniqlash"""
        from handlers.media_mgmt import extract_episode_num

        self.assertEqual(extract_episode_num(caption="15-qism"), 15)
        self.assertEqual(extract_episode_num(caption="qism 25"), 25)
        self.assertEqual(extract_episode_num(caption="Qism: 30"), 30)
        self.assertEqual(extract_episode_num(caption="Naruto 12-qism HD"), 12)
        self.assertEqual(extract_episode_num(caption="Ep 5"), 5)
        self.assertEqual(extract_episode_num(caption="Episode 42"), 42)
        self.assertEqual(extract_episode_num(caption="18-серия"), 18)
        self.assertEqual(extract_episode_num(caption="Серия 9"), 9)
        self.assertEqual(extract_episode_num(file_name="Naruto_S01E07_1080p.mp4"), 7)
        self.assertEqual(extract_episode_num(file_name="Anime_EP14.mkv"), 14)
        self.assertEqual(extract_episode_num(file_name="Series_23.mp4"), 23)
        self.assertEqual(extract_episode_num(caption="55"), 55)
        self.assertIsNone(extract_episode_num(caption="Ajoyib film premyerasi"))

    async def test_13_batch_episodes_atomic_addition(self):
        """Bir vaqtda 30 ta qismni ommaviy yuklash va 25 bepul / 5 pullik shartini tekshirish"""
        code = "BATCH_TEST_ANIME"
        await db.add_media(
            code=code,
            category="anime",
            title="Ommaviy Sinov Anime",
            file_id="ANIME_POSTER"
        )

        # 30 ta qism tayyorlash: 1-25 bepul, 26-30 premium
        episodes_batch = []
        for i in range(1, 31):
            is_prem = 1 if i > 25 else 0
            episodes_batch.append({
                "episode_num": i,
                "title": f"{i}-qism",
                "file_id": f"FILE_ID_EP_{i}",
                "file_type": "video",
                "is_premium": is_prem
            })

        count = await db.add_episodes_batch(code, episodes_batch)
        self.assertEqual(count, 30)

        saved = await db.get_episodes(code)
        self.assertEqual(len(saved), 30)

        # Qismlar narxini tekshirish: 1..25 bepul, 26..30 pullik
        for ep in saved:
            num = ep["episode_num"]
            if num <= 25:
                self.assertEqual(ep["is_premium"], 0, f"{num}-qism bepul bo'lishi kerak")
            else:
                self.assertEqual(ep["is_premium"], 1, f"{num}-qism premium bo'lishi kerak")

        await db.delete_media(code)

    async def test_14_user_auto_registration_on_premium_grant(self):
        """Oldin /start bosmagan begona userga Premium berilganda avtomatik ro'yxatga olinishi (0 rowcount xatosini oldini olish)"""
        ghost_user_id = 777888999
        # Foydalanuvchi bazada yo'qligini tekshiramiz
        u = await db.get_user(ghost_user_id)
        self.assertIsNone(u)

        # Premium beramiz
        ok = await db.set_user_premium(ghost_user_id, days=30)
        self.assertTrue(ok)

        # Endi foydalanuvchi bazada bor va premium faol
        is_prem = await db.is_user_premium(ghost_user_id)
        self.assertTrue(is_prem)

    async def test_15_payment_idempotency_and_duplicate_prevention(self):
        """Takroriy to'lov kelganda transaction_id orqali idempotentlikni ta'minlash"""
        tx_id = "test_stars_tx_unique_101"
        self.assertFalse(await db.is_transaction_processed(tx_id))

        ok1 = await db.record_payment(
            user_id=111111,
            amount="75",
            currency="XTR",
            provider="Telegram Stars",
            status="completed",
            transaction_id=tx_id
        )
        self.assertTrue(ok1)
        self.assertTrue(await db.is_transaction_processed(tx_id))

        # Ikkinchi marta o'sha transaction_id bilan kelsa rad etiladi
        ok2 = await db.record_payment(
            user_id=111111,
            amount="75",
            currency="XTR",
            provider="Telegram Stars",
            status="completed",
            transaction_id=tx_id
        )
        self.assertFalse(ok2)

    async def test_16_premium_pricing_and_payment_admin_settings(self):
        """Premium narxlari, karta va to'lov adminini sozlash"""
        await db.set_setting("premium_price_1m_uzs", "20 000")
        await db.set_setting("premium_price_1m_stars", "99")
        await db.set_setting("payment_admin_username", "super_seller")
        await db.set_setting("payment_card_number", "8600 9999 8888 7777")
        await db.set_setting("payment_card_holder", "Bunyodbek Sapayev")

        self.assertEqual(await db.get_setting("premium_price_1m_uzs"), "20 000")
        self.assertEqual(await db.get_setting("premium_price_1m_stars"), "99")
        self.assertEqual(await db.get_setting("payment_admin_username"), "super_seller")
        self.assertEqual(await db.get_setting("payment_card_number"), "8600 9999 8888 7777")
        self.assertEqual(await db.get_setting("payment_card_holder"), "Bunyodbek Sapayev")

    async def test_17_search_escaping_special_characters(self):
        """Qidiruvda % va _ belgilarini xavfsiz escape qilish va count_search_media"""
        code = "CODE_PERCENT_TEST"
        await db.add_media(
            code=code,
            category="kino",
            title="100% Qashqirlar_Makoni Film",
            file_id="TEST_FID_PERCENT"
        )

        res = await db.search_media("100%")
        self.assertTrue(any(m["code"] == code for m in res))

        total = await db.count_search_media("100%")
        self.assertGreaterEqual(total, 1)

        await db.delete_media(code)

    async def test_18_multi_super_admin_and_role_admin_check(self):
        """Ko'p sonli super adminlar va rollar bo'yicha adminlikni tekshirish"""
        test_admin_id = 9988776655
        self.assertFalse(await db.is_admin(test_admin_id))

        # Admin qo'shamiz
        ok = await db.add_admin(test_admin_id, role="admin", added_by=111111)
        self.assertTrue(ok)
        self.assertTrue(await db.is_admin(test_admin_id))

        # O'chirib tashlaymiz
        ok_rem = await db.remove_admin(test_admin_id)
        self.assertTrue(ok_rem)
        self.assertFalse(await db.is_admin(test_admin_id))

    async def test_19_admin_keyboards_safe_rendering(self):
        """Admin klaviaturalarining xavfsiz va to'g'ri shakllanishi"""
        from keyboards.inline import get_admin_keyboard
        from keyboards.reply import get_main_keyboard

        admin_inline = get_admin_keyboard()
        self.assertIsNotNone(admin_inline)
        self.assertTrue(len(admin_inline.inline_keyboard) > 5)

        main_reply = get_main_keyboard(is_admin=True)
        self.assertIsNotNone(main_reply)
        # ⚙️ Admin panel tugmasi mavjudligini tekshirish
        buttons_flat = [b.text for row in main_reply.keyboard for b in row]
        self.assertIn("⚙️ Admin panel", buttons_flat)
        self.assertIn("💎 Premium sozlamalari", buttons_flat)

    async def test_20_channel_subscription_and_social_media(self):
        """Telegram, Instagram va YouTube homiy kanallari tizimini tekshirish"""
        from utils.channel_check import (
            normalize_telegram_channel_id,
            normalize_instagram_link,
            normalize_youtube_link,
            get_subscription_keyboard,
            check_user_channels_subscription
        )

        # 1. Normalizatsiya tekshiruvi
        self.assertEqual(normalize_telegram_channel_id("https://t.me/kino_olami"), "@kino_olami")
        self.assertEqual(normalize_telegram_channel_id("t.me/kino_olami"), "@kino_olami")
        self.assertEqual(normalize_telegram_channel_id("kino_olami"), "@kino_olami")
        self.assertEqual(normalize_telegram_channel_id("@kino_olami"), "@kino_olami")
        self.assertEqual(normalize_telegram_channel_id("-1001234567890"), "-1001234567890")

        insta_un, insta_url = normalize_instagram_link("@kino_olami")
        self.assertEqual(insta_un, "@kino_olami")
        self.assertEqual(insta_url, "https://www.instagram.com/kino_olami/")

        yt_un, yt_url = normalize_youtube_link("@kino_olami")
        self.assertEqual(yt_un, "@kino_olami")
        self.assertEqual(yt_url, "https://www.youtube.com/@kino_olami")

        # 2. Bazaga Telegram, Instagram va YouTube qo'shish
        ok1 = await db.add_required_channel(
            channel_id="@test_tg_chan",
            channel_name="Telegram Kanal",
            invite_link="https://t.me/test_tg_chan",
            channel_type="telegram"
        )
        self.assertTrue(ok1)

        ok2 = await db.add_required_channel(
            channel_id="@test_insta",
            channel_name="Instagram Sahifa",
            invite_link="https://www.instagram.com/test_insta/",
            channel_type="instagram"
        )
        self.assertTrue(ok2)

        ok3 = await db.add_required_channel(
            channel_id="@test_yt",
            channel_name="YouTube Kanal",
            invite_link="https://www.youtube.com/@test_yt",
            channel_type="youtube"
        )
        self.assertTrue(ok3)

        # 3. Kanallarni olish va klaviatura shakllanishini tekshirish
        channels = await db.get_required_channels()
        self.assertGreaterEqual(len(channels), 3)

        kb = get_subscription_keyboard(channels)
        self.assertIsNotNone(kb)
        btn_texts = [b.text for row in kb.inline_keyboard for b in row]
        self.assertTrue(any("📢" in t for t in btn_texts))
        self.assertTrue(any("📸" in t for t in btn_texts))
        self.assertTrue(any("🔴" in t for t in btn_texts))
        self.assertTrue(any("✅ A'zo bo'ldim / Tekshirish" in t for t in btn_texts))

        # 4. Tozalash
        for ch in channels:
            await db.remove_required_channel(ch["channel_id"])

    async def test_22_cancel_logic_and_database_backup_restore(self):
        """Bekor qilish tekshiruvlari va zaxiralash/tiklash mexanizmi testi"""
        from handlers.start import is_cancel_message
        from workers.backup_manager import (
            verify_sqlite_database,
            perform_database_backup_file,
            restore_database_from_file_path,
            BACKUP_DIR
        )
        from pathlib import Path

        # 1. Bekor qilish so'zlari tekshiruvi
        self.assertTrue(is_cancel_message("❌ Bekor qilish"))
        self.assertTrue(is_cancel_message("Bekor qilish"))
        self.assertTrue(is_cancel_message("bekor"))
        self.assertTrue(is_cancel_message("/cancel"))
        self.assertTrue(is_cancel_message("  BEKOR QILISH  "))
        self.assertFalse(is_cancel_message("Avatar 2"))
        self.assertFalse(is_cancel_message("12345"))

        # 2. Baza zaxirasini yaratish testi
        backup_file = await perform_database_backup_file()
        self.assertIsNotNone(backup_file)
        self.assertTrue(backup_file.exists())
        self.assertGreater(backup_file.stat().st_size, 0)

        # 3. Yaratilgan zaxirani tekshirish
        is_valid, msg, media_cnt, user_cnt = verify_sqlite_database(backup_file)
        self.assertTrue(is_valid, f"Zaxira yaroqsiz: {msg}")
        self.assertGreaterEqual(media_cnt, 0)

        # 4. Tiklash mexanizmi testi
        ok, res_str = await restore_database_from_file_path(backup_file)
        self.assertTrue(ok)
        self.assertIn("muvaffaqiyatli", res_str.lower())

        # Tozalash
        if backup_file.exists():
            try:
                backup_file.unlink()
            except Exception:
                pass

if __name__ == "__main__":
    unittest.main()
