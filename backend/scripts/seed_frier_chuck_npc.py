"""Add Frier Chuck to Curse of Strahd as an NPC.

From D&D Beyond character 95993145 (Dave's). Deliberately created **without** a stat
block: the source sheet is an unfilled stub — all six ability scores identical, no AC,
no weapons, no background — so there are no real numbers to import. The narrative
record is created now; link a stat block later once the sheet is filled in.
"""

from __future__ import annotations

import os
import sys

# Ensure backend root is in search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.db import SessionLocal
from app.modules.campaign.models import Campaign
from app.modules.npcs.schemas import NpcCreate
from app.modules.npcs.service import create_npc

# Npc.stat_block_id carries an FK to stat_block, so that table has to be registered in
# SQLAlchemy's metadata before the flush. The app gets this free from main.py importing
# every module; a standalone script has to ask for it.
from app.modules.rules.models import StatBlock as _StatBlock  # noqa: F401

CAMPAIGN_ID = "019f51db-3552-7dd1-aba5-9180b3745bc5"  # Curse of Strahd
CREATED_BY = "019f4f7b-cc1e-72f1-a7b9-06da68bc5279"

NPC = NpcCreate(
    name="Frier Chuck",
    summary="Human cleric of the Life domain (level 3). Dave's character.",
    status="alive",
    goals=None,
    secrets=None,
)


def main() -> None:
    session = SessionLocal()
    try:
        campaign = session.get(Campaign, CAMPAIGN_ID)
        if campaign is None:
            raise SystemExit(f"campaign {CAMPAIGN_ID} not found")
        npc = create_npc(session, campaign, NPC, created_by=CREATED_BY)
        print(f"Created NPC {npc.entity_id} ({npc.name}) - no stat block linked")
    finally:
        session.close()


if __name__ == "__main__":
    main()
