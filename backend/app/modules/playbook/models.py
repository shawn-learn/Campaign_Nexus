from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Party(Base):
    """The adventuring party — one per campaign (docs/04, §6.6)."""

    __tablename__ = "party"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    #: Projection of ``party_moved`` — written only when a journey is committed.
    current_location_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entity.id", ondelete="SET NULL"), nullable=True
    )
    gold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inventory_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    reputation_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class Encounter(Base):
    """A reusable encounter (docs/04, §6.6). It *is* a wiki entity (so it can be linked to
    locations/quests via the knowledge graph); this row holds its structured combat data."""

    __tablename__ = "encounter"

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), primary_key=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    terrain: Mapped[str | None] = mapped_column(String, nullable=True)
    hazards: Mapped[str | None] = mapped_column(Text, nullable=True)
    tactics: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{"monster_id","count","side"}]
    combatants_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class Quest(Base):
    """Structured extension of a 'quest' wiki entity (docs/04, §6.6 / docs/05, §7.8).

    ``status`` is the authoritative-looking column of an event-derived machine (docs/06):
    every transition is written here *and* emitted as a ``quest_*`` domain event inside the
    same command transaction, so the timeline and this row can never disagree.
    Dependencies are not columns — they are acyclic ``depends_on`` links in the graph.
    """

    __tablename__ = "quest"

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), primary_key=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    quest_type: Mapped[str] = mapped_column(String, nullable=False, default="side")
    status: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    giver_npc_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("entity.id", ondelete="SET NULL"), nullable=True
    )
    rewards_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    #: Campaign time (seconds) at which the quest auto-expires; backed by a scheduled event.
    deadline_game: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Completion checklist: [{"text": str, "done": bool}]
    objectives_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class PartyMember(Base):
    """A PC in the party. ``status_json`` is live play-state (HP, conditions) shaped by the
    rules plugin — distinct from the character's definition in the stat block."""

    __tablename__ = "party_member"

    party_id: Mapped[str] = mapped_column(
        String, ForeignKey("party.id", ondelete="CASCADE"), primary_key=True
    )
    stat_block_id: Mapped[str] = mapped_column(
        String, ForeignKey("stat_block.id", ondelete="CASCADE"), primary_key=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    status_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    active: Mapped[bool] = mapped_column(Integer, nullable=False, default=True)


class CombatRun(Base):
    """One execution of an encounter — event-sourced (ADR-005). ``fold_cursor`` is the
    undo/redo pointer into ``combat_action.seq``."""

    __tablename__ = "combat_run"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    encounter_id: Mapped[str | None] = mapped_column(String, nullable=True)
    started_at_game: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # active | completed
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    fold_cursor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class CombatAction(Base):
    """One entry in a combat run's action log (the event-sourced state stream)."""

    __tablename__ = "combat_action"

    combat_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("combat_run.id", ondelete="CASCADE"), primary_key=True
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    recorded_at_real: Mapped[str] = mapped_column(String, nullable=False)
