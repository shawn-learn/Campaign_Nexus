"""Campaign bootstrap and reads.

Sprint 1 runs the local-first, single-user posture (ADR-011): on startup we ensure a
local user, a default rule system, and a demo campaign exist so the wiki endpoint has
a campaign to write into. Full campaign management arrives in Sprint 2.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.calendars import DEFAULT_CALENDAR
from app.core.clock import now_real_iso
from app.core.ids import new_id
from app.core.pipeline import command_tx
from app.modules.campaign.models import Campaign, CampaignMember, RuleSystem, User

LOCAL_USER_EMAIL = "local@campaign-nexus.local"
DEMO_CAMPAIGN_NAME = "Demo Campaign"


class UnknownRuleSystem(ValueError):
    pass


def ensure_bootstrap(session: Session) -> Campaign:
    """Idempotently create the local user, default rule system, and demo campaign."""
    user = session.scalar(select(User).where(User.email == LOCAL_USER_EMAIL))
    if user is None:
        user = User(
            id=new_id(),
            email=LOCAL_USER_EMAIL,
            display_name="Local GM",
            created_at_real=now_real_iso(),
        )
        session.add(user)

    rule_system = session.get(RuleSystem, "dnd5e")
    if rule_system is None:
        rule_system = RuleSystem(id="dnd5e", name="D&D 5e", version="0.0.0", enabled=True)
        session.add(rule_system)

    session.flush()

    campaign = session.scalar(select(Campaign).where(Campaign.name == DEMO_CAMPAIGN_NAME))
    if campaign is None:
        campaign = Campaign(
            id=new_id(),
            name=DEMO_CAMPAIGN_NAME,
            description="Seed campaign for the walking skeleton.",
            rule_system_id=rule_system.id,
            calendar_json=json.dumps(DEFAULT_CALENDAR),
            created_by=user.id,
            created_at_real=now_real_iso(),
        )
        session.add(campaign)
        session.flush()
        session.add(
            CampaignMember(campaign_id=campaign.id, user_id=user.id, role="owner")
        )

    session.commit()
    return campaign


def create_campaign(
    session: Session,
    *,
    name: str,
    description: str | None,
    rule_system_id: str,
    created_by: str,
) -> Campaign:
    """Create a campaign, make the creator its owner, and record ``campaign_created``."""
    if session.get(RuleSystem, rule_system_id) is None:
        raise UnknownRuleSystem(rule_system_id)

    now = now_real_iso()
    campaign = Campaign(
        id=new_id(),
        name=name,
        description=description,
        rule_system_id=rule_system_id,
        calendar_json=json.dumps(DEFAULT_CALENDAR),
        created_by=created_by,
        created_at_real=now,
    )
    session.add(campaign)
    session.add(CampaignMember(campaign_id=campaign.id, user_id=created_by, role="owner"))

    with command_tx(session, campaign.id, actor="gm") as ctx:
        ctx.emit(
            "campaign_created",
            payload={"campaign_id": campaign.id, "name": name, "rule_system_id": rule_system_id},
            narrative=f"Campaign '{name}' created.",
        )

    session.refresh(campaign)
    return campaign


def list_campaigns(session: Session) -> list[Campaign]:
    return list(session.scalars(select(Campaign).order_by(Campaign.created_at_real)))


def get_local_user_id(session: Session) -> str:
    user = session.scalar(select(User).where(User.email == LOCAL_USER_EMAIL))
    if user is None:
        raise RuntimeError("bootstrap not run: local user missing")
    return user.id
