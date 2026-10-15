"""Runtime Stats Service — live load figures for whoever is chasing a slow app.

Platform-level and super-admin only: the figures describe the whole process
(every community's sockets and workers), so no community admin may read them.
"""

from typing import Any, Dict, Optional

from application.services.auth_service import AuthService
from application.utils import runtime_stats
from models import User


class RuntimeStatsService:
    @staticmethod
    async def snapshot(actor: Optional[User]) -> Dict[str, Any]:
        await AuthService.ensure_super_admin(actor)
        return runtime_stats.collect()
