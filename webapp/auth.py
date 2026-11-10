import hmac
import hashlib
import json
from urllib.parse import parse_qsl
from typing import Optional, Dict, Any
from config import BOT_TOKEN
from database import db

def validate_init_data(init_data: str, bot_token: str = BOT_TOKEN) -> Optional[Dict[str, Any]]:
    """
    Telegram WebApp initData ni xavfsiz tekshirish (HMAC SHA-256).
    """
    if not init_data:
        return None
        
    try:
        parsed_data = dict(parse_qsl(init_data, strict_parsing=True))
    except Exception:
        return None

    if "hash" not in parsed_data:
        return None

    received_hash = parsed_data.pop("hash")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
    
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    if hmac.compare_digest(calculated_hash, received_hash):
        # auth_date tekshiruvi: 24 soatdan (86400 soniya) oshgan bo'lsa qabul qilinmaydi (Replay attack himoyasi)
        auth_date = parsed_data.get("auth_date")
        if auth_date:
            try:
                import time
                auth_ts = int(auth_date)
                current_ts = int(time.time())
                if (current_ts - auth_ts > 86400) or (auth_ts - current_ts > 300):
                    return None
            except (ValueError, TypeError):
                return None

        user_str = parsed_data.get("user")
        if user_str:
            try:
                return json.loads(user_str)
            except Exception:
                return None
        return parsed_data
    return None

async def verify_admin_access(init_data: str) -> Optional[Dict[str, Any]]:
    """
    initData-ni tekshiradi va foydalanuvchi admin ekanligiga ishonch hosil qiladi.
    Agar admin bo'lsa user ma'lumotlarini qaytaradi, aks holda None.
    """
    user = validate_init_data(init_data)
    if not user or "id" not in user:
        return None
        
    user_id = int(user["id"])
    is_admin = await db.is_admin(user_id)
    if not is_admin:
        return None

    return user
