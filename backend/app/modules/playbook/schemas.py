from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.modules.time.schemas import ClockOut, FiredEvent


class PartyMemberOut(BaseModel):
    stat_block_id: str
    name: str
    #: Live play-state, shaped by the rules plugin — its keys are system-specific.
    status: dict[str, Any]
    #: The plugin's reading of ``status``, so the UI never has to know those keys.
    hp: int = 0
    max_hp: int = 0
    active: bool


class PartyOut(BaseModel):
    id: str
    current_location_id: str | None = None
    current_location_name: str | None = None
    current_map_id: str | None = None
    current_x: float | None = None
    current_y: float | None = None
    #: Wealth in copper (exact); ``gold`` is the whole-gp view and ``wealth_label``
    #: the human breakdown, e.g. "12 gp 3 sp 5 cp".
    wealth_cp: int
    gold: int
    wealth_label: str
    inventory: list[Any]
    reputation: dict[str, Any]
    #: What this system calls its rests (5e: short/long; Nimble: field/safe).
    rest_types: list[str] = []
    members: list[PartyMemberOut]


class PartyPatch(BaseModel):
    #: Set exact wealth in copper. ``gold`` (whole gp) is accepted for convenience
    #: and is treated as ``gold * 100`` copper.
    wealth_cp: int | None = None
    gold: int | None = None
    current_location_id: str | None = None
    current_map_id: str | None = None
    current_x: float | None = None
    current_y: float | None = None
    location_set: bool = False
    coordinates_set: bool = False


class LocationConnectionOut(BaseModel):
    from_location_id: str
    from_location_name: str | None
    to_location_id: str
    to_location_name: str | None
    distance: float
    terrain: str


class LocationConnectionCreate(BaseModel):
    from_location_id: str
    to_location_id: str
    distance: float
    terrain: str = "road"


class AddMember(BaseModel):
    stat_block_id: str
    #: Starting HP; defaults to the sheet's maximum. Deliberately not `current_hit_points` —
    #: that is 5e's word for it, and the plugin decides where the number lands in `status`.
    hit_points: int | None = None


class RestRequest(BaseModel):
    # Not an enum: the legal rests are whatever the campaign's plugin declares. The service
    # validates against ``rest_types()`` — 5e's short/long are not the schema's business.
    rest_type: str = Field(min_length=1)


class RestResult(BaseModel):
    rest_type: str
    from_time: int
    to_time: int
    members: list[PartyMemberOut]


# --- travel (FR-5.3) -------------------------------------------------------- #
class TravelLeg(BaseModel):
    distance: float = Field(gt=0)
    terrain: str = "road"
    pace: str = "normal"
    conveyance: str = "foot"
    to_location_id: str | None = None
    travel_type: str = "normal"


class TravelLegOut(TravelLeg):
    duration_seconds: int
    to_location_name: str | None = None


class TravelRequest(BaseModel):
    legs: list[TravelLeg] = Field(min_length=1)
    #: Skip the overnight long rests a multi-day journey would otherwise insert.
    forced_march: bool = False


class ForcedMarchSave(BaseModel):
    #: Cumulative travel-hour across the whole journey (1-based).
    hour: int
    #: Which day of travel this save falls on (DCs reset each day).
    day: int = 1
    dc: int


class TravelPlan(BaseModel):
    legs: list[TravelLegOut]
    travel_seconds: int
    rest_stops: int
    rest_seconds: int
    total_seconds: int
    depart_at_game: int
    arrive_at_game: int
    arrive_at_label: str
    distance_unit: str
    forced_march: bool
    #: What the world does while the party is on the road (shown *before* committing).
    would_fire: list[FiredEvent]
    destination_id: str | None
    destination_name: str | None
    forced_march_saves: list[ForcedMarchSave] = []


class TravelResult(BaseModel):
    from_time: int
    to_time: int
    rest_stops: int
    destination_id: str | None
    destination_name: str | None
    plan: TravelPlan


class CombatantSpec(BaseModel):
    monster_id: str
    count: int = Field(default=1, ge=1)
    side: str = Field(default="foe", pattern="^(foe|ally)$")


class EncounterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    terrain: str | None = None
    hazards: str | None = None
    tactics: str | None = None
    combatants: list[CombatantSpec] = []
    location_id: str | None = None  # optional 'located_at' link


class EncounterUpdate(BaseModel):
    terrain: str | None = None
    hazards: str | None = None
    tactics: str | None = None
    combatants: list[CombatantSpec] | None = None


class EncounterCombatantOut(BaseModel):
    monster_id: str
    name: str
    count: int
    side: str


class DifficultyOut(BaseModel):
    supported: bool
    difficulty: str | None = None
    total_xp: int | None = None
    adjusted_xp: int | None = None
    party_size: int | None = None
    thresholds: dict[str, int] | None = None


class EncounterOut(BaseModel):
    id: str
    name: str
    terrain: str | None
    hazards: str | None
    tactics: str | None
    combatants: list[EncounterCombatantOut]
    difficulty: DifficultyOut
    location_id: str | None


# --- skill challenges (FR-12.x) -------------------------------------------- #
#: The difficulty tiers a challenge authors against; the rules plugin prices each as a DC.
DIFFICULTY_TIERS = ("trivial", "easy", "normal", "hard", "very_hard", "nearly_impossible")
#: How a single recorded check turned out. Criticals count as their non-critical sibling for
#: success/failure tallies but let the UI surface flavour (e.g. a Vecna whisper on a crit).
CHECK_OUTCOMES = ("success", "failure", "critical_success", "critical_failure")

_DIFFICULTY_PATTERN = "^(" + "|".join(DIFFICULTY_TIERS) + ")$"
_OUTCOME_PATTERN = "^(" + "|".join(CHECK_OUTCOMES) + ")$"


def _difficulty_field() -> Any:
    return Field(default="normal", pattern=_DIFFICULTY_PATTERN)


class SkillApproach(BaseModel):
    skill: str = Field(min_length=1, max_length=80)
    difficulty: str = _difficulty_field()
    hint: str | None = None


class GraduatedOutcome(BaseModel):
    #: This outcome applies when failures are ≥ this and less than the next tier's threshold.
    min_failures: int = Field(ge=0)
    label: str = Field(min_length=1, max_length=120)
    narrative: str = ""
    #: Free-form mechanical consequences the GM applies by hand (e.g. "Party starts Slowed").
    effects: list[str] = []


class SkillChallengeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    premise: str | None = None
    total_checks: int = Field(default=0, ge=0)
    success_target: int | None = Field(default=None, ge=1)
    failure_cap: int | None = Field(default=None, ge=1)
    approaches: list[SkillApproach] = []
    outcomes: list[GraduatedOutcome] = []
    location_id: str | None = None  # optional 'located_at' link


class SkillChallengeUpdate(BaseModel):
    premise: str | None = None
    total_checks: int | None = Field(default=None, ge=0)
    success_target: int | None = Field(default=None, ge=1)
    failure_cap: int | None = Field(default=None, ge=1)
    approaches: list[SkillApproach] | None = None
    outcomes: list[GraduatedOutcome] | None = None


class SkillChallengeOut(BaseModel):
    id: str
    name: str
    premise: str | None
    total_checks: int
    success_target: int | None
    failure_cap: int | None
    approaches: list[SkillApproach]
    outcomes: list[GraduatedOutcome]
    #: The DCs this campaign's rule system assigns each difficulty tier — the UI shows them
    #: next to each approach without hard-coding any system's numbers.
    dcs: dict[str, int]
    location_id: str | None


class CheckRecord(BaseModel):
    skill: str = Field(default="", max_length=80)
    difficulty: str = _difficulty_field()
    #: The DC actually used; the service fills it from the plugin when omitted.
    dc: int | None = None
    outcome: str = Field(pattern=_OUTCOME_PATTERN)
    actor: str | None = None
    note: str | None = None


class RecordCheckIn(BaseModel):
    skill: str = Field(default="", max_length=80)
    difficulty: str = _difficulty_field()
    outcome: str = Field(pattern=_OUTCOME_PATTERN)
    #: Override the plugin's DC for this one check (e.g. an ad-hoc call at the table).
    dc: int | None = None
    actor: str | None = None
    note: str | None = None


class StartSkillRun(BaseModel):
    challenge_id: str | None = None


class SkillChallengeRunOut(BaseModel):
    run_id: str
    challenge_id: str | None
    challenge_name: str | None
    status: str  # active | resolved
    checks: list[CheckRecord]
    successes: int
    failures: int
    checks_made: int
    #: How many more checks the graduated form runs before it resolves (None in race mode).
    checks_remaining: int | None
    #: The outcome tier the current failure count maps to — shown live as a projection while
    #: active, and the final reading once ``status == "resolved"``.
    outcome: GraduatedOutcome | None
    resolved: bool


# --- random tables (FR-12.x) ----------------------------------------------- #
class TableRow(BaseModel):
    #: Inclusive roll range for dice mode (ignored in weighted mode).
    min: int | None = None
    max: int | None = None
    #: Relative weight for weighted mode (dice == "").
    weight: int | None = Field(default=None, ge=1)
    text: str = Field(default="", max_length=2000)
    #: A result can link to any entity — an encounter to run, an NPC, or another table.
    target_entity_id: str | None = None


class TableRowOut(TableRow):
    target_name: str | None = None
    target_type: str | None = None


class RandomTableCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    #: ``NdM`` (e.g. "1d20", "d100") for range tables; "" for weighted tables.
    dice: str = Field(default="1d20", max_length=20)
    rows: list[TableRow] = []


class RandomTableUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    dice: str | None = Field(default=None, max_length=20)
    rows: list[TableRow] | None = None


class RandomTableOut(BaseModel):
    id: str
    name: str
    dice: str
    rows: list[TableRowOut]
    row_count: int


class RollOut(BaseModel):
    #: The number rolled (None in weighted mode).
    roll: int | None
    #: Index of the selected row, or None if nothing matched the roll.
    index: int | None
    text: str
    target_entity_id: str | None = None
    target_name: str | None = None
    target_type: str | None = None


# --- combat ---------------------------------------------------------------- #
class Combatant(BaseModel):
    id: str
    name: str
    side: str
    max_hp: int
    hp: int
    temp_hp: int
    initiative: int
    conditions: list[str]
    concentrating: bool
    defeated: bool


class CombatState(BaseModel):
    round: int
    turn_index: int
    order: list[str]
    combatants: dict[str, Combatant]


class CombatRunOut(BaseModel):
    run_id: str
    encounter_id: str | None
    status: str
    cursor: int
    total_actions: int
    can_undo: bool
    can_redo: bool
    state: CombatState
    #: combatant id → stat-block id, so the UI can show a combatant's full stat block.
    combatant_blocks: dict[str, str] = {}


class CombatRunBrief(BaseModel):
    run_id: str
    encounter_id: str | None
    status: str
    round: int


class StartCombat(BaseModel):
    encounter_id: str | None = None


class CombatActionIn(BaseModel):
    action_type: str
    payload: dict[str, Any] = {}


class CombatSummary(BaseModel):
    rounds: int
    duration_seconds: int
    defeated: list[str]
    to_time: int


# --------------------------------------------------------------------------- #
# Live session dashboard (FR-14) — one composite read for the run-the-table view
# --------------------------------------------------------------------------- #
class EntityBrief(BaseModel):
    id: str
    name: str
    entity_type: str
    summary: str | None = None


# --- quests (FR-10) --------------------------------------------------------- #
class Objective(BaseModel):
    text: str
    done: bool = False


class QuestBrief(EntityBrief):
    status: str
    quest_type: str
    deadline_game: int | None = None
    deadline_label: str | None = None
    overdue: bool = False


class QuestOut(BaseModel):
    entity_id: str
    name: str
    summary: str | None
    quest_type: str
    status: str
    giver_npc_id: str | None
    giver_name: str | None
    rewards: dict[str, Any]
    deadline_game: int | None
    deadline_label: str | None
    overdue: bool
    objectives: list[Objective]
    depends_on: list[str]
    unlocks: list[str]
    #: Prerequisites that are not yet completed — non-empty means the quest is blocked.
    blocked_by: list[str]


class QuestCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    summary: str | None = None
    quest_type: str = "side"
    status: str = "unknown"
    giver_npc_id: str | None = None
    rewards: dict[str, Any] = {}
    deadline_game: int | None = None
    objectives: list[Objective] = []


class QuestUpdate(BaseModel):
    quest_type: str | None = None
    giver_npc_id: str | None = None
    rewards: dict[str, Any] | None = None
    deadline_game: int | None = None
    objectives: list[Objective] | None = None


class QuestStatusIn(BaseModel):
    status: str


class ObjectiveToggle(BaseModel):
    index: int = Field(ge=0)
    done: bool = True


class DependencyIn(BaseModel):
    depends_on_id: str


class QuestNode(BaseModel):
    id: str
    name: str
    status: str
    quest_type: str
    overdue: bool


class QuestEdge(BaseModel):
    id: str
    #: Prerequisite → dependent, so the graph reads left-to-right in play order.
    source: str
    target: str


class QuestGraph(BaseModel):
    nodes: list[QuestNode]
    edges: list[QuestEdge]


class EventBrief(BaseModel):
    id: str
    event_type: str
    narrative: str
    occurred_at_game: int
    recorded_at_real: str


class DashboardSession(BaseModel):
    id: str
    session_number: int
    status: str


class DashboardOut(BaseModel):
    clock: ClockOut
    session: DashboardSession | None
    party: PartyOut
    active_quests: list[QuestBrief]
    current_location: EntityBrief | None
    npcs_here: list[EntityBrief]
    encounters_here: list[EntityBrief]
    pinned: list[EntityBrief]
    recent_events: list[EventBrief]
    notes: list[EventBrief]
    active_combat: CombatRunOut | None


class SetLocation(BaseModel):
    entity_id: str | None = None


class SetPin(BaseModel):
    entity_id: str
    pinned: bool = True
