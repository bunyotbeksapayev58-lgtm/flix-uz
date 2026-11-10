from aiogram import Router
from .start import router as start_router
from .movies import router as movies_router
from .premium import router as premium_router
from .admin import router as admin_router
from .media_mgmt import router as media_mgmt_router
from .admin_mgmt import router as admin_mgmt_router
from .support import router as support_router
from .extra import router as extra_router
from .requests import router as requests_router
from .inline_query import router as inline_router

def setup_routers() -> Router:
    main_router = Router()
    main_router.include_router(start_router)
    main_router.include_router(admin_router)
    main_router.include_router(media_mgmt_router)
    main_router.include_router(admin_mgmt_router)
    main_router.include_router(premium_router)
    main_router.include_router(support_router)
    main_router.include_router(requests_router)
    main_router.include_router(inline_router)
    main_router.include_router(extra_router)
    main_router.include_router(movies_router)
    return main_router

__all__ = ["setup_routers"]
