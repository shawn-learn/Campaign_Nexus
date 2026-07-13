"""Skill challenges (FR-12) — a system-agnostic non-combat scene resolved by a run of skill
checks, with a graduated outcome keyed on how many failures the party took.

A challenge *is* a wiki entity (so it links into the knowledge graph) plus this structured
data. Difficulty tiers are priced into concrete DCs by the campaign's rules plugin
(``skill_check_dcs``), so the same authored challenge reads as 5e's DCs or Nimble's without
either system leaking into the feature.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.modules.campaign.models import Campaign
from app.modules.playbook.models import SkillChallenge, SkillChallengeRun
from app.modules.playbook.schemas import (
    CheckRecord,
    GraduatedOutcome,
    RecordCheckIn,
    SkillApproach,
    SkillChallengeOut,
    SkillChallengeRunOut,
)
from app.modules.rules import registry
from app.modules.wiki import service as wiki_service
from app.modules.wiki.models import Entity, Link
from app.modules.wiki.schemas import EntityCreate

LOCATED_AT = "located_at"

#: Fallback ladder for a campaign whose rule system isn't installed (mirrors Base's default).
_DEFAULT_DCS = {
    "trivial": 5, "easy": 10, "normal": 15, "hard": 20, "very_hard": 25, "nearly_impossible": 30,
}

# Outcomes success/failure tallies treat a critical as its plain sibling.
_SUCCESSES = {"success", "critical_success"}
_FAILURES = {"failure", "critical_failure"}


class SkillChallengeNotFound(LookupError):
    pass


class SkillRunNotFound(LookupError):
    pass


class SkillRunClosed(RuntimeError):
    pass


def _dcs(campaign: Campaign) -> dict[str, int]:
    if registry.has_system(campaign.rule_system_id):
        return dict(registry.get_system(campaign.rule_system_id).skill_check_dcs())
    return dict(_DEFAULT_DCS)


def _location_id(session: Session, challenge_id: str) -> str | None:
    return session.scalar(
        select(Link.to_entity).where(
            Link.from_entity == challenge_id, Link.link_type_id == LOCATED_AT
        )
    )


# --------------------------------------------------------------------------- #
# Definitions
# --------------------------------------------------------------------------- #
def to_out(
    session: Session, campaign: Campaign, challenge: SkillChallenge
) -> SkillChallengeOut:
    entity = session.get(Entity, challenge.entity_id)
    approaches = [SkillApproach(**a) for a in json.loads(challenge.approaches_json)]
    outcomes = [GraduatedOutcome(**o) for o in json.loads(challenge.outcomes_json)]
    return SkillChallengeOut(
        id=challenge.entity_id,
        name=entity.name if entity else "",
        premise=challenge.premise,
        total_checks=challenge.total_checks,
        success_target=challenge.success_target,
        failure_cap=challenge.failure_cap,
        approaches=approaches,
        outcomes=_sorted_outcomes(outcomes),
        dcs=_dcs(campaign),
        location_id=_location_id(session, challenge.entity_id),
    )


def _sorted_outcomes(outcomes: list[GraduatedOutcome]) -> list[GraduatedOutcome]:
    return sorted(outcomes, key=lambda o: o.min_failures)


def create_skill_challenge(
    session: Session,
    campaign: Campaign,
    *,
    name: str,
    premise: str | None,
    total_checks: int,
    success_target: int | None,
    failure_cap: int | None,
    approaches: list[SkillApproach],
    outcomes: list[GraduatedOutcome],
    location_id: str | None,
    created_by: str,
) -> SkillChallengeOut:
    entity = wiki_service.create_entity(
        session, campaign.id,
        data=EntityCreate(entity_type="skill_challenge", name=name), created_by=created_by,
    )
    challenge = SkillChallenge(
        entity_id=entity.id,
        campaign_id=campaign.id,
        premise=premise,
        total_checks=total_checks,
        success_target=success_target,
        failure_cap=failure_cap,
        approaches_json=json.dumps([a.model_dump() for a in approaches]),
        outcomes_json=json.dumps([o.model_dump() for o in outcomes]),
    )
    session.add(challenge)
    session.commit()

    if location_id:
        wiki_service.create_link(
            session, campaign.id, entity.id, to_entity=location_id, link_type_id=LOCATED_AT
        )
    return to_out(session, campaign, challenge)


def _require(session: Session, campaign_id: str, challenge_id: str) -> SkillChallenge:
    challenge = session.get(SkillChallenge, challenge_id)
    if challenge is None or challenge.campaign_id != campaign_id:
        raise SkillChallengeNotFound(challenge_id)
    return challenge


def get_skill_challenge(
    session: Session, campaign: Campaign, challenge_id: str
) -> SkillChallengeOut:
    return to_out(session, campaign, _require(session, campaign.id, challenge_id))


def list_skill_challenges(
    session: Session, campaign: Campaign
) -> list[SkillChallengeOut]:
    rows = session.scalars(
        select(SkillChallenge).where(SkillChallenge.campaign_id == campaign.id)
    )
    return [to_out(session, campaign, c) for c in rows]


def update_skill_challenge(
    session: Session,
    campaign: Campaign,
    challenge_id: str,
    *,
    premise: str | None,
    total_checks: int | None,
    success_target: int | None,
    failure_cap: int | None,
    approaches: list[SkillApproach] | None,
    outcomes: list[GraduatedOutcome] | None,
) -> SkillChallengeOut:
    challenge = _require(session, campaign.id, challenge_id)
    if premise is not None:
        challenge.premise = premise
    if total_checks is not None:
        challenge.total_checks = total_checks
    if success_target is not None:
        challenge.success_target = success_target
    if failure_cap is not None:
        challenge.failure_cap = failure_cap
    if approaches is not None:
        challenge.approaches_json = json.dumps([a.model_dump() for a in approaches])
    if outcomes is not None:
        challenge.outcomes_json = json.dumps([o.model_dump() for o in outcomes])
    session.commit()
    return to_out(session, campaign, challenge)


# --------------------------------------------------------------------------- #
# Runs — the live tracker
# --------------------------------------------------------------------------- #
def _run_challenge(
    session: Session, campaign_id: str, run: SkillChallengeRun
) -> SkillChallenge | None:
    if run.challenge_id is None:
        return None
    challenge = session.get(SkillChallenge, run.challenge_id)
    if challenge is not None and challenge.campaign_id == campaign_id:
        return challenge
    return None


def _select_outcome(
    outcomes: list[GraduatedOutcome], failures: int
) -> GraduatedOutcome | None:
    """The tier whose ``min_failures`` is the greatest not exceeding ``failures``."""
    chosen: GraduatedOutcome | None = None
    for outcome in _sorted_outcomes(outcomes):
        if outcome.min_failures <= failures:
            chosen = outcome
        else:
            break
    return chosen


def _is_resolved(challenge: SkillChallenge | None, successes: int, failures: int) -> bool:
    if challenge is None:
        return False
    if challenge.failure_cap is not None and failures >= challenge.failure_cap:
        return True
    if challenge.success_target is not None and successes >= challenge.success_target:
        return True
    return challenge.total_checks > 0 and (successes + failures) >= challenge.total_checks


def _run_out(
    session: Session, campaign_id: str, run: SkillChallengeRun
) -> SkillChallengeRunOut:
    challenge = _run_challenge(session, campaign_id, run)
    checks_raw: list[dict[str, Any]] = json.loads(run.checks_json)
    checks = [CheckRecord(**c) for c in checks_raw]
    successes = sum(1 for c in checks if c.outcome in _SUCCESSES)
    failures = sum(1 for c in checks if c.outcome in _FAILURES)

    outcomes = (
        [GraduatedOutcome(**o) for o in json.loads(challenge.outcomes_json)]
        if challenge
        else []
    )
    checks_remaining: int | None = None
    if challenge and challenge.total_checks > 0:
        checks_remaining = max(0, challenge.total_checks - len(checks))

    name = None
    if challenge is not None:
        entity = session.get(Entity, challenge.entity_id)
        name = entity.name if entity else None

    return SkillChallengeRunOut(
        run_id=run.id,
        challenge_id=run.challenge_id,
        challenge_name=name,
        status=run.status,
        checks=checks,
        successes=successes,
        failures=failures,
        checks_made=len(checks),
        checks_remaining=checks_remaining,
        outcome=_select_outcome(outcomes, failures),
        resolved=run.status == "resolved",
    )


def start_run(
    session: Session, campaign: Campaign, challenge_id: str | None
) -> SkillChallengeRunOut:
    if challenge_id is not None:
        _require(session, campaign.id, challenge_id)  # 404s an unknown/foreign challenge
    run = SkillChallengeRun(
        id=new_id(),
        campaign_id=campaign.id,
        challenge_id=challenge_id,
        status="active",
        checks_json="[]",
    )
    session.add(run)
    session.commit()
    return _run_out(session, campaign.id, run)


def _require_run(
    session: Session, campaign_id: str, run_id: str
) -> SkillChallengeRun:
    run = session.get(SkillChallengeRun, run_id)
    if run is None or run.campaign_id != campaign_id:
        raise SkillRunNotFound(run_id)
    return run


def get_run(session: Session, campaign: Campaign, run_id: str) -> SkillChallengeRunOut:
    return _run_out(session, campaign.id, _require_run(session, campaign.id, run_id))


def record_check(
    session: Session, campaign: Campaign, run_id: str, body: RecordCheckIn
) -> SkillChallengeRunOut:
    run = _require_run(session, campaign.id, run_id)
    if run.status != "active":
        raise SkillRunClosed(run_id)

    dc = body.dc if body.dc is not None else _dcs(campaign).get(body.difficulty)
    checks: list[dict[str, Any]] = json.loads(run.checks_json)
    checks.append(
        CheckRecord(
            skill=body.skill, difficulty=body.difficulty, dc=dc,
            outcome=body.outcome, actor=body.actor, note=body.note,
        ).model_dump()
    )
    run.checks_json = json.dumps(checks)

    challenge = _run_challenge(session, campaign.id, run)
    successes = sum(1 for c in checks if c["outcome"] in _SUCCESSES)
    failures = sum(1 for c in checks if c["outcome"] in _FAILURES)
    if _is_resolved(challenge, successes, failures):
        run.status = "resolved"
    session.commit()
    return _run_out(session, campaign.id, run)


def undo_check(session: Session, campaign: Campaign, run_id: str) -> SkillChallengeRunOut:
    run = _require_run(session, campaign.id, run_id)
    checks: list[dict[str, Any]] = json.loads(run.checks_json)
    if checks:
        checks.pop()
    run.checks_json = json.dumps(checks)
    run.status = "active"  # undoing a check re-opens a run that had just resolved
    session.commit()
    return _run_out(session, campaign.id, run)


def resolve_run(session: Session, campaign: Campaign, run_id: str) -> SkillChallengeRunOut:
    """Manually end a run early (e.g. the party bailed) at whatever tier it has reached."""
    run = _require_run(session, campaign.id, run_id)
    run.status = "resolved"
    session.commit()
    return _run_out(session, campaign.id, run)
