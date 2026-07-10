"""Travel planner (FR-5.3, docs/07 §9.5): legs → preview → commit.

Distance and pace come from the GM; how fast that *is* comes from the rules plugin's
``travel_pace_table`` — the planner itself knows nothing about miles-per-day or difficult
terrain. A system that ships no table (``simpletest``) simply reports travel unsupported,
exactly as it does for encounter difficulty.

Preview is a pure calculation plus a dry run of the time engine, so the GM can see *before
committing* that they would arrive two days after the festival starts. Committing advances
the clock (firing everything en route), inserts overnight long rests unless the party is
force-marching, and records ``party_traveled`` + ``party_moved``.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.pipeline import command_tx
from app.modules.campaign.models import Campaign
from app.modules.playbook import service as party_service
from app.modules.playbook.schemas import (
    TravelLeg,
    TravelLegOut,
    TravelPlan,
    TravelRequest,
    TravelResult,
)
from app.modules.rules import registry
from app.modules.rules.interface import TravelPaceTable
from app.modules.time import service as time_service
from app.modules.wiki.models import Entity


class TravelUnsupported(ValueError):
    pass


class TravelError(ValueError):
    pass


class _Table:
    """A typed view over the plugin's untyped ``TravelPaceTable``.

    The interface is deliberately a plain dict (plugins are pure data), so this is the one
    place that asserts its shape — the planner below never touches raw keys.
    """

    def __init__(self, raw: TravelPaceTable) -> None:
        self.paces: dict[str, dict[str, float]] = raw.get("paces", {})
        self.terrain: dict[str, float] = raw.get("terrain", {})
        self.distance_unit: str = str(raw.get("distance_unit", ""))
        self.travel_day_seconds: int = int(float(raw.get("hours_per_travel_day", 8)) * 3600)

    def leg_seconds(self, leg: TravelLeg) -> int:
        if leg.pace not in self.paces:
            raise TravelError(f"unknown pace '{leg.pace}'")
        conveyances = self.paces[leg.pace]
        if leg.conveyance not in conveyances:
            raise TravelError(f"unknown conveyance '{leg.conveyance}'")
        if leg.terrain not in self.terrain:
            raise TravelError(f"unknown terrain '{leg.terrain}'")

        per_day = conveyances[leg.conveyance] * self.terrain[leg.terrain]
        if per_day <= 0:  # pragma: no cover - a plugin would have to say 0 miles/day
            raise TravelError(f"'{leg.terrain}' is impassable by {leg.conveyance}")
        # distance / (distance per travel-day) = travel-days, each `travel_day_seconds` long.
        return round(leg.distance / per_day * self.travel_day_seconds)


def _table(campaign: Campaign) -> _Table:
    raw = registry.get_system(campaign.rule_system_id).travel_pace_table()
    if not raw.get("supported"):
        raise TravelUnsupported(f"{campaign.rule_system_id} has no travel rules")
    return _Table(raw)


def plan(session: Session, campaign: Campaign, body: TravelRequest) -> TravelPlan:
    """Cost the route and dry-run the clock across it. Writes nothing."""
    table = _table(campaign)
    if not body.legs:
        raise TravelError("a journey needs at least one leg")

    legs: list[TravelLegOut] = []
    travel_seconds = 0
    for leg in body.legs:
        seconds = table.leg_seconds(leg)
        travel_seconds += seconds
        destination = session.get(Entity, leg.to_location_id) if leg.to_location_id else None
        legs.append(TravelLegOut(
            **leg.model_dump(), duration_seconds=seconds,
            to_location_name=destination.name if destination else None,
        ))

    # Multi-day journeys stop for the night, unless the party force-marches (§9.5).
    system = registry.get_system(campaign.rule_system_id)
    rest_seconds = 0
    rest_stops = 0
    per_day = table.travel_day_seconds
    overnight = system.overnight_rest_type()
    if not body.forced_march and per_day > 0 and overnight:
        rest_stops = max(0, (travel_seconds - 1) // per_day)
        rest_seconds = rest_stops * system.rest_duration_seconds(overnight)

    total = travel_seconds + rest_seconds
    cal = time_service.calendar_for(campaign)
    arrival = campaign.clock_time_game + total

    destination_id = body.legs[-1].to_location_id
    destination = session.get(Entity, destination_id) if destination_id else None
    if destination_id and (destination is None or destination.campaign_id != campaign.id):
        raise TravelError("destination not found in this campaign")

    return TravelPlan(
        legs=legs,
        travel_seconds=travel_seconds,
        rest_stops=rest_stops,
        rest_seconds=rest_seconds,
        total_seconds=total,
        depart_at_game=campaign.clock_time_game,
        arrive_at_game=arrival,
        arrive_at_label=cal.format(arrival)["label"],
        distance_unit=table.distance_unit,
        forced_march=body.forced_march,
        # What the GM most wants to see: the world does not wait for them.
        would_fire=time_service.preview_advance(
            session, campaign, delta_seconds=total
        ).would_fire,
        destination_id=destination_id,
        destination_name=destination.name if destination else None,
    )


def _route(preview: TravelPlan) -> str:
    """A readable route: named waypoints if the GM gave them, else distance and terrain."""
    named = [leg.to_location_name for leg in preview.legs if leg.to_location_name]
    if len(named) == len(preview.legs):
        return "to " + " → ".join(named)
    total = sum(leg.distance for leg in preview.legs)
    unit = preview.distance_unit or "units"
    tail = f" to {named[-1]}" if named else ""
    return f"{total:g} {unit}{tail}"


def commit(session: Session, campaign: Campaign, body: TravelRequest) -> TravelResult:
    """Execute the plan: advance through the journey, rest overnight, arrive."""
    preview = plan(session, campaign, body)
    from_time = campaign.clock_time_game

    per_day = _table(campaign).travel_day_seconds
    overnight = registry.get_system(campaign.rule_system_id).overnight_rest_type()

    # Walk the journey in day-sized bites so an overnight rest lands *between* them and the
    # party benefits from it (rather than arriving exhausted and resting afterwards).
    remaining = preview.travel_seconds
    rests_taken = 0
    while remaining > 0:
        chunk = min(remaining, per_day) if per_day > 0 else remaining
        time_service.advance_time(
            session, campaign, delta_seconds=chunk, reason="travel"
        )
        remaining -= chunk
        more_rests = rests_taken < preview.rest_stops
        if remaining > 0 and overnight and not body.forced_march and more_rests:
            party_service.rest(session, campaign.id, overnight)
            rests_taken += 1
            session.refresh(campaign)

    session.refresh(campaign)
    party = party_service.get_or_create_party(session, campaign.id)
    with command_tx(session, campaign.id, actor="gm") as ctx:
        ctx.emit(
            "party_traveled",
            payload={"legs": [leg.model_dump() for leg in preview.legs],
                     "duration_seconds": campaign.clock_time_game - from_time,
                     "rest_stops": rests_taken, "forced_march": body.forced_march},
            narrative=(
                f"The party traveled {_route(preview)}"
                f"{' by forced march' if body.forced_march else ''}."
            ),
        )
        if preview.destination_id:
            party.current_location_id = preview.destination_id
            ctx.emit(
                "party_moved",
                payload={"to": preview.destination_id},
                narrative=f"The party arrived at {preview.destination_name}.",
                subject_entity_ids=(preview.destination_id,),
            )

    return TravelResult(
        from_time=from_time,
        to_time=campaign.clock_time_game,
        rest_stops=rests_taken,
        destination_id=preview.destination_id,
        destination_name=preview.destination_name,
        plan=preview,
    )
