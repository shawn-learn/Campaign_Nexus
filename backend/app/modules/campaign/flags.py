"""Campaign flag storage. Callers emit ``flag_changed`` inside their command tx."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.campaign.models import CampaignFlag


def list_flags(session: Session, campaign_id: str) -> dict[str, Any]:
    rows = session.scalars(
        select(CampaignFlag).where(CampaignFlag.campaign_id == campaign_id)
    )
    return {r.key: json.loads(r.value_json) for r in rows}


def set_flag(
    session: Session, campaign_id: str, key: str, value: Any, *, at_game: int
) -> tuple[Any, Any]:
    """Upsert a flag; returns (old_value, new_value). No event is emitted here."""
    flag = session.get(CampaignFlag, {"campaign_id": campaign_id, "key": key})
    old = json.loads(flag.value_json) if flag is not None else None
    if flag is None:
        flag = CampaignFlag(
            campaign_id=campaign_id, key=key, value_json=json.dumps(value), updated_at_game=at_game
        )
        session.add(flag)
    else:
        flag.value_json = json.dumps(value)
        flag.updated_at_game = at_game
    session.flush()
    return old, value
