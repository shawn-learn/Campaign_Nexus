"""Single import site that pulls every ORM model into ``Base.metadata``.

Alembic's env and the test schema builder both import this so autogenerate and
``create_all`` see the complete schema. Add new model modules here as they land.
"""

from __future__ import annotations

from app.core.db import Base
from app.core.domain_event import DomainEvent  # noqa: F401
from app.modules.atlas.models import Map, MapMarker, MapRegion, Media  # noqa: F401
from app.modules.campaign.models import (  # noqa: F401
    Campaign,
    CampaignFlag,
    CampaignMember,
    RuleSystem,
    User,
)
from app.modules.chronicle import projectors as _chronicle_projectors  # noqa: F401  (registers)
from app.modules.chronicle.models import (  # noqa: F401
    Session,
    TimelineEntity,
    TimelineEntry,
)
from app.modules.equipment import projectors as _equipment_projectors  # noqa: F401  (registers)
from app.modules.equipment.models import (  # noqa: F401
    Equipment,
    Item,
    ItemOwnershipHistory,
    LibraryEntry,
)
from app.modules.merchant.models import Merchant, MerchantStock  # noqa: F401
from app.modules.npcs import projectors as _npc_projectors  # noqa: F401  (registers)
from app.modules.npcs import service as _npc_service  # noqa: F401  (registers move_npc)
from app.modules.npcs.models import Npc, NpcLocationHistory, NpcSchedule  # noqa: F401
from app.modules.playbook import quests as _playbook_quests  # noqa: F401  (registers action)
from app.modules.playbook.models import (  # noqa: F401
    CombatAction,
    CombatRoll,
    CombatRun,
    Encounter,
    Party,
    PartyMember,
    Quest,
    RandomTable,
    SkillChallenge,
    SkillChallengeRun,
)
from app.modules.rules.models import Monster, StatBlock  # noqa: F401
from app.modules.story.models import StoryEdge, StoryNode  # noqa: F401
from app.modules.time.models import ScheduledEvent  # noqa: F401
from app.modules.wiki.models import (  # noqa: F401
    ArticleSnapshot,
    Entity,
    EntityTag,
    Link,
    LinkType,
    Tag,
)

metadata = Base.metadata

__all__ = ["Base", "metadata"]
