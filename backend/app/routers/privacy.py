"""
The facts the privacy notice quotes (BUG-033): who the controller is and how long
data is kept. Public: the notice must be readable before signing in. The text
itself lives in the frontend (pages/PrivacyPage.tsx).
"""

import logging

from fastapi import APIRouter

from ..config import settings
from ..schemas import PrivacyInfo

router = APIRouter(tags=["privacy"])
logger = logging.getLogger(__name__)

REQUIRED = {
    "privacy_controller": "PRIVACY_CONTROLLER",
    "privacy_controller_id": "PRIVACY_CONTROLLER_ID",
    "privacy_controller_address": "PRIVACY_CONTROLLER_ADDRESS",
    "privacy_contact": "PRIVACY_CONTACT",
}


def missing_settings() -> list[str]:
    """Settings the notice can't do without (GDPR art. 13.1.a): empty until filled in."""
    return [env for attr, env in REQUIRED.items() if not getattr(settings, attr).strip()]


@router.get("/privacy", response_model=PrivacyInfo)
def privacy():
    return PrivacyInfo(
        controller=settings.privacy_controller.strip(),
        controller_id=settings.privacy_controller_id.strip(),
        controller_address=settings.privacy_controller_address.strip(),
        contact=settings.privacy_contact.strip(),
        dpo=settings.privacy_dpo.strip(),
        audit_retention_days=settings.audit_retention_days,
        backup_keep_days=settings.backup_keep_days,
        session_days=settings.session_days,
        groups_refresh_hours=settings.groups_refresh_hours,
        missing=missing_settings(),
    )
