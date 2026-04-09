from __future__ import annotations

import hmac

from app.core.config import settings


class AdminService:
    def verify_password(self, candidate: str | None) -> bool:
        expected = (settings.admin_password or "").strip()
        provided = (candidate or "").strip()
        if not expected:
            return False
        return hmac.compare_digest(provided, expected)


admin_service = AdminService()
