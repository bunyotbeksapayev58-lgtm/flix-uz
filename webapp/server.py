import os
import re
import json
import asyncio
from typing import Optional
from pathlib import Path
from aiohttp import web
from aiogram import Bot

from config import BOT_TOKEN, BASE_DIR
from database import db
from .auth import verify_admin_access, validate_init_data

STATIC_DIR = Path(__file__).resolve().parent / "static"

def json_response(data: dict, status: int = 200) -> web.Response:
    return web.Response(
        text=json.dumps(data, ensure_ascii=False),
        content_type="application/json",
        status=status,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "Content-Type, X-Telegram-Init-Data"
        }
    )

class AdminWebApp:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.app = web.Application()
        self.setup_routes()

    def setup_routes(self):
        # Asosiy sahifa
        self.app.router.add_get("/", self.handle_index)
        self.app.router.add_options("/{tail:.*}", self.handle_options)

        # API endpointlar
        self.app.router.add_post("/api/auth/verify", self.api_auth_verify)
        self.app.router.add_get("/api/stats", self.api_get_stats)
        
        # Media (Kino, Serial, Anime, Drama)
        self.app.router.add_get("/api/media", self.api_get_media)
        self.app.router.add_post("/api/media", self.api_add_media)
        self.app.router.add_put("/api/media/{code}", self.api_update_media)
        self.app.router.add_delete("/api/media/{code}", self.api_delete_media)
        self.app.router.add_post("/api/media/{code}/toggle-access", self.api_toggle_access)

        # Qismlar (Episodes for Serial & Anime)
        self.app.router.add_get("/api/media/{code}/episodes", self.api_get_episodes)
        self.app.router.add_post("/api/media/{code}/episodes", self.api_add_episode)
        self.app.router.add_post("/api/media/{code}/episodes/batch", self.api_add_episodes_batch)
        self.app.router.add_post("/api/media/{code}/episodes/threshold", self.api_set_episodes_threshold)
        self.app.router.add_delete("/api/episodes/{id}", self.api_delete_episode)

        # Majburiy homiy kanallari
        self.app.router.add_get("/api/channels", self.api_get_channels)
        self.app.router.add_post("/api/channels", self.api_add_channel)
        self.app.router.add_delete("/api/channels/{id}", self.api_delete_channel)

        # Foydalanuvchilar
        self.app.router.add_get("/api/users", self.api_get_users)
        self.app.router.add_post("/api/users/{id}/toggle-block", self.api_toggle_block_user)
        self.app.router.add_post("/api/users/{id}/grant-premium", self.api_grant_premium)
        self.app.router.add_post("/api/users/{id}/toggle-admin", self.api_toggle_admin_user)

        # Adminlar
        self.app.router.add_get("/api/admins", self.api_get_admins)
        self.app.router.add_post("/api/admins", self.api_add_admin)
        self.app.router.add_delete("/api/admins/{id}", self.api_delete_admin)

        # Xabar tarqatish (Broadcast)
        self.app.router.add_post("/api/broadcast", self.api_broadcast)

        # Statik fayllar (agar mavjud bo'lsa)
        if STATIC_DIR.exists():
            self.app.router.add_static("/static/", path=str(STATIC_DIR), name="static")

    async def handle_options(self, request: web.Request) -> web.Response:
        return web.Response(
            status=204,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
                "Access-Control-Allow-Headers": "Content-Type, X-Telegram-Init-Data"
            }
        )

    async def get_verified_user(self, request: web.Request) -> Optional[dict]:
        """Sarlavhadan initData-ni olib, tekshirilgan foydalanuvchini qaytaradi"""
        init_data = request.headers.get("X-Telegram-Init-Data", "").strip()
        if not init_data:
            return None
        return await verify_admin_access(init_data)

    async def check_admin_header(self, request: web.Request) -> bool:
        """So'rovdan faqat sarlavha (header) orqali adminlikni tekshiradi"""
        user = await self.get_verified_user(request)
        return user is not None

    async def check_super_admin_header(self, request: web.Request) -> bool:
        """Faqat Super Admin huquqini tekshiradi"""
        user = await self.get_verified_user(request)
        if not user:
            return False
        return await db.is_super_admin(int(user["id"]))

    async def handle_index(self, request: web.Request) -> web.Response:
        index_file = STATIC_DIR / "index.html"
        if not index_file.exists():
            return web.Response(text="Admin Mini App index.html fayli topilmadi.", status=404)
        return web.FileResponse(index_file)

    # ==================== AUTH ====================
    async def api_auth_verify(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return json_response({"ok": False, "error": "Noto'g'ri JSON format"}, 400)

        init_data = data.get("initData", "")
        if not init_data:
            return json_response({
                "ok": False,
                "error": "⛔️ initData taqdim etilmadi!"
            }, 401)

        admin_user = await verify_admin_access(init_data)
        if not admin_user:
            return json_response({
                "ok": False,
                "error": "⛔️ Ruxsat berilmadi! Siz bot administratori emassiz yoki sessiya eskirgan."
            }, 403)

        user_id = int(admin_user["id"])
        is_super = await db.is_super_admin(user_id)

        return json_response({
            "ok": True,
            "user": admin_user,
            "is_super_admin": is_super
        })

    # ==================== STATS ====================
    async def api_get_stats(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        stats = await db.get_overall_stats()
        monthly = await db.get_monthly_users_count()
        stats["monthly_active_users"] = monthly

        return json_response({"ok": True, "stats": stats})

    # ==================== MEDIA ====================
    async def api_get_media(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        category = request.query.get("category", "").lower().strip()
        search = request.query.get("search", "").strip()
        try:
            page = max(1, int(request.query.get("page", 1)))
            limit = min(50, max(5, int(request.query.get("limit", 15))))
        except (ValueError, TypeError):
            return json_response({"ok": False, "error": "Noto'g'ri page yoki limit parametri"}, 400)

        offset = (page - 1) * limit

        if search:
            items = await db.search_media(search, limit=limit, offset=offset)
            total = await db.count_search_media(search)
        elif category and category in ["kino", "serial", "anime", "drama"]:
            items = await db.get_media_by_category(category, limit=limit, offset=offset)
            total = await db.count_media_by_category(category)
        else:
            items = await db.get_all_media(limit=limit, offset=offset)
            total = await db.get_total_media_count()

        return json_response({
            "ok": True,
            "items": items,
            "total": total,
            "page": page,
            "limit": limit
        })

    async def api_add_media(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        try:
            data = await request.json()
        except Exception:
            return json_response({"ok": False, "error": "Noto'g'ri JSON"}, 400)

        required = ["code", "category", "title", "file_id"]
        for r in required:
            if not data.get(r):
                return json_response({"ok": False, "error": f"'{r}' maydoni to'ldirilishi shart!"}, 400)

        code = str(data["code"]).strip()
        existing = await db.get_media_by_code(code)
        if existing:
            return json_response({"ok": False, "error": f"'{code}' kodi allaqachon mavjud!"}, 400)

        ok = await db.add_media(
            code=code,
            category=data["category"].lower().strip(),
            title=data["title"].strip(),
            original_title=data.get("original_title", ""),
            poster_file_id=data.get("poster_file_id", ""),
            duration=data.get("duration", ""),
            language=data.get("language", "O'zbekcha"),
            age_rating=data.get("age_rating", "12+"),
            genre=data.get("genre", ""),
            year=str(data.get("year", "")),
            description=data.get("description", ""),
            file_id=data["file_id"].strip(),
            file_type=data.get("file_type", "video"),
            is_premium=int(data.get("is_premium", 0))
        )

        if ok:
            return json_response({"ok": True, "message": "Media muvaffaqiyatli saqlandi!"})
        return json_response({"ok": False, "error": "Saqlashda xatolik yuz berdi"}, 500)

    async def api_update_media(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        code = request.match_info["code"]
        try:
            data = await request.json()
        except Exception:
            return json_response({"ok": False, "error": "Noto'g'ri JSON"}, 400)

        ok = await db.update_media(
            code=code,
            title=data.get("title", ""),
            genre=data.get("genre", ""),
            year=str(data.get("year", "")),
            description=data.get("description", ""),
            is_premium=int(data.get("is_premium", 0))
        )
        if ok:
            return json_response({"ok": True, "message": "Yangilandi!"})
        return json_response({"ok": False, "error": "Media topilmadi"}, 404)

    async def api_delete_media(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        code = request.match_info["code"]
        ok = await db.delete_media(code)
        if ok:
            return json_response({"ok": True, "message": f"'{code}' o'chirildi!"})
        return json_response({"ok": False, "error": "Media topilmadi"}, 404)

    async def api_toggle_access(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        code = request.match_info["code"]
        new_val = await db.toggle_media_access(code)
        if new_val is not None:
            return json_response({
                "ok": True,
                "is_premium": new_val,
                "status": "⭐ Premium" if new_val == 1 else "🆓 Bepul"
            })
        return json_response({"ok": False, "error": "Media topilmadi"}, 404)

    # ==================== QISMLAR (EPISODES) ====================
    async def api_get_episodes(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        code = request.match_info["code"]
        episodes = await db.get_episodes(code)
        return json_response({"ok": True, "episodes": episodes})

    async def api_add_episode(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        code = request.match_info["code"]
        try:
            data = await request.json()
        except Exception:
            return json_response({"ok": False, "error": "Noto'g'ri JSON"}, 400)

        episode_num = data.get("episode_num")
        file_id = data.get("file_id", "").strip()
        if not episode_num or not file_id:
            return json_response({"ok": False, "error": "Qism raqami va Video Fayl ID kiritilishi shart!"}, 400)

        ok = await db.add_episode(
            media_code=code,
            episode_num=int(episode_num),
            season_num=int(data.get("season_num", 1)),
            title=data.get("title", ""),
            file_id=file_id
        )
        return json_response({"ok": True, "message": "Qism qo'shildi!"})

    async def api_add_episodes_batch(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        code = request.match_info["code"]
        try:
            data = await request.json()
        except Exception:
            return json_response({"ok": False, "error": "Noto'g'ri JSON"}, 400)

        episodes_to_add = []
        if "batch_text" in data:
            raw_text = str(data["batch_text"]).strip()
            start_ep = int(data.get("start_ep", 1))
            free_up_to = int(data.get("free_up_to", 0))
            lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
            curr_ep = start_ep
            for line in lines:
                m = re.match(r'^(\d+)\s*[:\-–]\s*(.+)$', line)
                if m:
                    ep_num = int(m.group(1))
                    fid = m.group(2).strip()
                    if ep_num >= curr_ep:
                        curr_ep = ep_num + 1
                else:
                    ep_num = curr_ep
                    curr_ep += 1
                    fid = line.strip()

                if len(fid) >= 10:
                    is_prem = 1 if (free_up_to > 0 and ep_num > free_up_to) else 0
                    episodes_to_add.append({
                        "episode_num": ep_num,
                        "title": f"{ep_num}-qism",
                        "file_id": fid,
                        "file_type": "video",
                        "is_premium": is_prem
                    })
        elif "episodes" in data and isinstance(data["episodes"], list):
            for item in data["episodes"]:
                if isinstance(item, dict) and item.get("file_id"):
                    ep_num = int(item.get("episode_num", 1))
                    episodes_to_add.append({
                        "episode_num": ep_num,
                        "title": item.get("title", f"{ep_num}-qism"),
                        "file_id": str(item["file_id"]).strip(),
                        "file_type": item.get("file_type", "video"),
                        "is_premium": int(item.get("is_premium", 0))
                    })

        if not episodes_to_add:
            return json_response({"ok": False, "error": "Yaroqli qismlar yoki File ID lar topilmadi!"}, 400)

        count = await db.add_episodes_batch(code, episodes_to_add)
        return json_response({
            "ok": True,
            "added_count": count,
            "message": f"{count} ta qism muvaffaqiyatli saqlandi!"
        })

    async def api_delete_episode(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        ep_id = int(request.match_info["id"])
        ok = await db.delete_episode(ep_id)
        if ok:
            return json_response({"ok": True, "message": "Qism o'chirildi!"})
        return json_response({"ok": False, "error": "Qism topilmadi"}, 404)

    async def api_set_episodes_threshold(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        code = request.match_info["code"]
        try:
            data = await request.json()
        except Exception:
            return json_response({"ok": False, "error": "Noto'g'ri JSON"}, 400)

        free_up_to = int(data.get("free_up_to", 0))
        await db.set_episodes_access_threshold(code, free_up_to)
        return json_response({
            "ok": True,
            "message": f"1-{free_up_to} qismlar bepul, qolganlari ⭐ Premium qilib belgilandi!" if free_up_to > 0 else "Barcha qismlar bepul qilindi!"
        })

    # ==================== HOMIY KANALLAR ====================
    async def api_get_channels(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        channels = await db.get_required_channels()
        return json_response({"ok": True, "channels": channels})

    async def api_add_channel(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        try:
            data = await request.json()
        except Exception:
            return json_response({"ok": False, "error": "Noto'g'ri JSON"}, 400)

        ch_id = data.get("channel_id", "").strip()
        ch_name = data.get("channel_name", "").strip()
        invite_link = data.get("invite_link", "").strip()

        if not ch_id:
            return json_response({"ok": False, "error": "Kanal ID yoki @username kiritilishi shart!"}, 400)

        ok = await db.add_required_channel(ch_id, ch_name, invite_link)
        if ok:
            return json_response({"ok": True, "message": "Kanal muvaffaqiyatli qo'shildi!"})
        return json_response({"ok": False, "error": "Kanal allaqachon mavjud yoki xatolik yuz berdi"}, 400)

    async def api_delete_channel(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        ch_id = request.match_info["id"]
        ok = await db.remove_required_channel(ch_id)
        if ok:
            return json_response({"ok": True, "message": "Kanal o'chirildi!"})
        return json_response({"ok": False, "error": "Kanal topilmadi"}, 404)

    # ==================== FOYDALANUVCHILAR ====================
    async def api_get_users(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        search = request.query.get("search", "")
        page = max(1, int(request.query.get("page", 1)))
        limit = min(100, max(10, int(request.query.get("limit", 20))))
        offset = (page - 1) * limit

        users = await db.get_users_filtered(search=search, limit=limit, offset=offset)
        total = await db.get_total_users_count()

        return json_response({
            "ok": True,
            "users": users,
            "total": total,
            "page": page,
            "limit": limit
        })

    async def api_toggle_block_user(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        user_id = int(request.match_info["id"])
        user = await db.get_user(user_id)
        if not user:
            return json_response({"ok": False, "error": "Foydalanuvchi topilmadi"}, 404)

        if user["is_blocked"]:
            await db.unblock_user(user_id)
            return json_response({"ok": True, "is_blocked": False, "message": "Blokdan chiqarildi!"})
        else:
            await db.block_user(user_id)
            return json_response({"ok": True, "is_blocked": True, "message": "Bloklandi!"})

    async def api_grant_premium(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        user_id = int(request.match_info["id"])
        try:
            data = await request.json()
            days = int(data.get("days", 30))
        except Exception:
            days = 30

        ok = await db.set_user_premium(user_id, days=days)
        if ok:
            try:
                await self.bot.send_message(
                    user_id,
                    f"🎉 Sizga administrator tomonidan <b>{days} kunlik Premium obuna</b> faollashtirildi!",
                    parse_mode="HTML"
                )
            except Exception:
                pass
            return json_response({"ok": True, "message": f"{days} kunlik Premium berildi!"})
        return json_response({"ok": False, "error": "Foydalanuvchi topilmadi"}, 404)

    async def api_toggle_admin_user(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        user_id = int(request.match_info["id"])
        is_adm = await db.is_admin(user_id)
        if is_adm:
            super_id = await db.get_super_admin_id()
            if user_id == super_id:
                return json_response({"ok": False, "error": "Bosh adminni olib tashlab bo'lmaydi!"}, 400)
            await db.remove_admin(user_id)
            return json_response({"ok": True, "is_admin": False, "message": "Adminlikdan olib tashlandi!"})
        else:
            await db.add_admin(user_id, added_by=0)
            try:
                await self.bot.send_message(
                    user_id,
                    "👑 Siz @FlixUzCinemaBot botida Teng Huquqli Administrator etib tayinlandingiz!\n/admin buyrug'i va Mini Appdan foydalanishingiz mumkin."
                )
            except Exception:
                pass
            return json_response({"ok": True, "is_admin": True, "message": "Teng huquqli Admin etib tayinlandi!"})

    # ==================== ADMINLAR ====================
    async def api_get_admins(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        admins = await db.get_all_admins()
        super_admin_id = await db.get_super_admin_id()
        admin_data = []
        for aid in admins:
            user = await db.get_user(aid)
            admin_data.append({
                "id": aid,
                "first_name": user["first_name"] if user else "Admin",
                "username": user["username"] if user else "",
                "is_super_admin": (aid == super_admin_id)
            })

        return json_response({"ok": True, "admins": admin_data})

    async def api_add_admin(self, request: web.Request) -> web.Response:
        if not await self.check_super_admin_header(request):
            return json_response({"ok": False, "error": "⛔️ Faqat Super Admin yangi admin tayinlashi mumkin!"}, 403)

        try:
            data = await request.json()
            raw_input = str(data["user_id"]).strip()
        except Exception:
            return json_response({"ok": False, "error": "Foydalanuvchi ID yoki @username kiritilishi shart!"}, 400)

        target_id = None
        if raw_input.isdigit():
            target_id = int(raw_input)
        else:
            clean_un = raw_input.lstrip("@").strip()
            found = await db.get_user_by_username(clean_un)
            if found:
                target_id = found["id"]
            else:
                return json_response({"ok": False, "error": f"@{clean_un} topilmadi. U botga kirgan bo'lishi kerak!"}, 404)

        ok = await db.add_admin(target_id, added_by=0)
        if ok:
            try:
                await self.bot.send_message(
                    target_id,
                    "👑 Siz @FlixUzCinemaBot botida Teng Huquqli Administrator etib tayinlandingiz!\n/admin buyrug'i va Mini Appdan foydalanishingiz mumkin."
                )
            except Exception:
                pass
            return json_response({"ok": True, "message": f"{target_id} muvaffaqiyatli teng huquqli admin etib tayinlandi!"})
        return json_response({"ok": False, "error": "Bu foydalanuvchi allaqachon admin"}, 400)

    async def api_delete_admin(self, request: web.Request) -> web.Response:
        if not await self.check_super_admin_header(request):
            return json_response({"ok": False, "error": "⛔️ Faqat Super Admin adminni o'chira oladi!"}, 403)

        try:
            target_id = int(request.match_info["id"])
        except (ValueError, KeyError):
            return json_response({"ok": False, "error": "Noto'g'ri ID parametri"}, 400)

        super_id = await db.get_super_admin_id()
        if target_id == super_id:
            return json_response({"ok": False, "error": "Bosh adminni o'chirib bo'lmaydi!"}, 400)

        ok = await db.remove_admin(target_id)
        if ok:
            return json_response({"ok": True, "message": "Admin o'chirildi!"})
        return json_response({"ok": False, "error": "Admin topilmadi"}, 404)

    # ==================== BROADCAST (XABAR YUBORISH) ====================
    async def api_broadcast(self, request: web.Request) -> web.Response:
        if not await self.check_admin_header(request):
            return json_response({"ok": False, "error": "Ruxsat berilmadi"}, 403)

        try:
            data = await request.json()
            text = data.get("text", "").strip()
        except Exception:
            return json_response({"ok": False, "error": "Matn kiritilmadi"}, 400)

        if not text:
            return json_response({"ok": False, "error": "Xabar matni bo'sh bo'lishi mumkin emas!"}, 400)

        user_ids = await db.get_all_user_ids()
        total = len(user_ids)
        sent = 0
        failed = 0

        user = await self.get_verified_user(request)
        admin_id = int(user["id"]) if user else 0

        # Orqa fonda xabar jo'natish
        async def run_broadcast():
            nonlocal sent, failed
            from aiogram.exceptions import TelegramRetryAfter
            for uid in user_ids:
                try:
                    await self.bot.send_message(uid, text, parse_mode="HTML")
                    sent += 1
                except TelegramRetryAfter as e:
                    await asyncio.sleep(e.retry_after)
                    try:
                        await self.bot.send_message(uid, text, parse_mode="HTML")
                        sent += 1
                    except Exception:
                        failed += 1
                except Exception:
                    failed += 1
                await asyncio.sleep(0.05) # Telegram spam protection

            if admin_id:
                try:
                    await self.bot.send_message(
                        admin_id,
                        f"📊 <b>Xabar tarqatish yakunlandi!</b>\n\n"
                        f"👥 Jami qamrov: {total} ta\n"
                        f"✅ Muvaffaqiyatli: {sent} ta\n"
                        f"❌ Yetib bormadi: {failed} ta",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

        asyncio.create_task(run_broadcast())

        return json_response({
            "ok": True,
            "message": f"Xabar tarqatish boshlandi! Jami {total} ta foydalanuvchiga yuborilmoqda."
        })

def create_admin_app(bot: Bot) -> web.Application:
    admin_app = AdminWebApp(bot)
    return admin_app.app
