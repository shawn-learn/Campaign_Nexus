from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String, Text
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
    current_map_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("map.entity_id", ondelete="SET NULL"), nullable=True
    )
    current_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: Party wealth in copper pieces (the smallest coin), so sp/cp are tracked
    #: exactly; the API also exposes a whole-gp view and a formatted breakdown.
    wealth_cp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inventory_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    reputation_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class LocationConnection(Base):
    """Predefined distances and travel properties between locations (e.g. roads, trails)."""

    __tablename__ = "location_connection"

    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), primary_key=True
    )
    from_location_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), primary_key=True
    )
    to_location_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), primary_key=True
    )
    distance: Mapped[float] = mapped_column(Float, nullable=False)
    terrain: Mapped[str] = mapped_column(String, nullable=False, default="road")


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


class SkillChallenge(Base):
    """A reusable *skill challenge* (docs/04, §6.6) — a system-agnostic non-combat scene
    resolved by a sequence of skill checks. Like an encounter it *is* a wiki entity (so it
    links into the knowledge graph); this row holds its structured data.

    The scene is graduated: the GM runs checks until a resolution condition is met, then reads
    the outcome whose ``min_failures`` is the greatest value not exceeding the failures taken.
    ``approaches_json`` are the suggested skill options (each with a *difficulty tier* the
    rules plugin maps to a concrete DC), and ``outcomes_json`` the graduated result tiers.

    Resolution supports two shapes, both generalizable across rule systems:
    * *graduated* — set ``total_checks``: resolve once that many checks have been made.
    * *race*      — set ``success_target`` and/or ``failure_cap``: resolve on either bound.
    """

    __tablename__ = "skill_challenge"

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), primary_key=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Narrative set-up / read-aloud shown when the challenge begins.
    premise: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: Graduated mode: how many checks are made before the scene resolves (0 = unused).
    total_checks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Race mode: successes that end the scene early in the party's favour.
    success_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Race mode: failures that end the scene early against the party.
    failure_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: [{"skill","difficulty","hint"}] — suggested approaches (difficulty is a tier key).
    approaches_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    #: [{"min_failures","label","narrative","effects":[str]}] — graduated outcome tiers.
    outcomes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class SkillChallengeRun(Base):
    """One live run of a skill challenge at the table. ``checks_json`` is the ordered log of
    checks the GM has recorded; popping the last entry is the run's undo. It resolves to the
    outcome selected from the challenge's tiers once a resolution condition is met."""

    __tablename__ = "skill_challenge_run"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: The challenge being run; nullable so a deleted definition doesn't orphan-delete history.
    challenge_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("skill_challenge.entity_id", ondelete="SET NULL"), nullable=True
    )
    # active | resolved
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    #: [{"skill","difficulty","dc","outcome","actor","note"}] — outcome ∈ success|failure|
    #: critical_success|critical_failure.
    checks_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


class RandomTable(Base):
    """A GM roll table (FR-12.x) — a wiki entity plus its rows, so a result can *link* to
    another entity (an encounter to run, an NPC to introduce, or another table to nest).

    ``dice`` selects the mode: an ``NdM`` expression (e.g. ``1d20``, ``d100``) means the rows
    carry inclusive ``min``/``max`` ranges matched against the roll; an empty ``dice`` means
    weighted selection by each row's ``weight``.
    """

    __tablename__ = "random_table"

    entity_id: Mapped[str] = mapped_column(
        String, ForeignKey("entity.id", ondelete="CASCADE"), primary_key=True
    )
    campaign_id: Mapped[str] = mapped_column(
        String, ForeignKey("campaign.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: Dice expression (``NdM``); empty string = weighted mode.
    dice: Mapped[str] = mapped_column(String, nullable=False, default="1d20")
    #: [{"min","max","weight","text","target_entity_id"}] — rows in author order.
    rows_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")


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


class CombatRoll(Base):
    """A die rolled during a combat — a *record*, deliberately outside the fold.

    Rolls are not state: nothing about the combat changes because a d20 came up 17. Logging
    them as ``combat_action`` rows would give each one a ``fold_cursor`` slot, so Undo after
    an attack would step back over the roll and appear to do nothing. Here instead, the log
    is append-only and undo never un-rolls a die — which is also the honest model, since a
    roll that happened at the table cannot be taken back.

    The resulting action carries ``roll_id`` in its payload (the reducer ignores it), so
    "where did this 8 damage come from" stays answerable.
    """

    __tablename__ = "combat_roll"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    combat_run_id: Mapped[str] = mapped_column(
        String, ForeignKey("combat_run.id", ondelete="CASCADE"), index=True, nullable=False
    )
    #: The folded-state combatant id — not an FK: combatants live in the log, not a table.
    combatant_id: Mapped[str | None] = mapped_column(String, nullable=True)
    #: initiative | attack | damage | save | death_save
    kind: Mapped[str] = mapped_column(String, nullable=False)
    #: What was rolled, for the log: "Greatclub", "CON save", "Initiative".
    label: Mapped[str] = mapped_column(String, nullable=False, default="")
    expression: Mapped[str] = mapped_column(String, nullable=False)
    #: normal | advantage | disadvantage
    mode: Mapped[str] = mapped_column(String, nullable=False, default="normal")
    #: The individual faces + modifier, so the UI can show "17 (17, 9) + 5".
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    #: The AC or DC this was rolled against, when there was one.
    target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: hit | miss | crit | fumble | success | failure — None when there was no target.
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    recorded_at_real: Mapped[str] = mapped_column(String, nullable=False)
