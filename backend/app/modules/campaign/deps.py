"""Campaign-scoped authorization — the single gate every scoped route passes through.

Per NFR-6.2 all data access is campaign-scoped and role-checked in one place, so there
is no unscoped code path to audit. In the Sprint 2 local-first posture (ADR-011) the
"current user" is always the bootstrapped local user; when real authentication lands
(Sprint 2+ / P-LAN) only ``_current_user_id`` changes — the role logic is unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.campaign.models import Campaign, CampaignMember
from app.modules.campaign.service import get_local_user_id

# viewer < editor < owner
_ROLE_RANK = {"viewer": 1, "editor": 2, "owner": 3}


@dataclass(frozen=True)
class CampaignContext:
    campaign_id: str
    user_id: str
    role: str


def _current_user_id(session: Session) -> str:
    # Local-first: the single bootstrapped user. Replaced by session auth later.
    return get_local_user_id(session)


def require_campaign_role(min_role: str) -> Callable[..., CampaignContext]:
    """Build a dependency that asserts the current user has >= ``min_role`` on the campaign."""
    required_rank = _ROLE_RANK[min_role]

    def dependency(
        campaign_id: str = Path(...),
        session: Session = Depends(get_session),
    ) -> CampaignContext:
        campaign = session.get(Campaign, campaign_id)
        if campaign is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")

        user_id = _current_user_id(session)
        member = session.scalar(
            select(CampaignMember).where(
                CampaignMember.campaign_id == campaign_id,
                CampaignMember.user_id == user_id,
            )
        )
        # 404 (not 403) on non-membership: don't reveal that a campaign exists to
        # someone who can't see it (tenant isolation).
        if member is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "campaign not found")
        if _ROLE_RANK[member.role] < required_rank:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"requires {min_role} role on this campaign"
            )
        return CampaignContext(campaign_id=campaign_id, user_id=user_id, role=member.role)

    return dependency
