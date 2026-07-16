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

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.pipeline import command_tx
from app.modules.atlas.models import MapMarker, MapRegion
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


# Travel type mappings
TRAVEL_TYPES = {
    "normal": {"pace": "normal", "conveyance": "foot", "difficult_terrain": False, "gallop": False},
    "forced march": {"pace": "normal", "conveyance": "foot", "difficult_terrain": False, "gallop": False},
    "mounted": {"pace": "normal", "conveyance": "horse", "difficult_terrain": False, "gallop": False},
    "gallop difficult terrain": {"pace": "normal", "conveyance": "horse", "difficult_terrain": True, "gallop": True},
    "slow (sneak)": {"pace": "slow", "conveyance": "foot", "difficult_terrain": False, "gallop": False},
    "mounted difficult terrain": {"pace": "normal", "conveyance": "horse", "difficult_terrain": True, "gallop": False},
    "difficult terrain": {"pace": "normal", "conveyance": "foot", "difficult_terrain": True, "gallop": False},
}

RULES_DETAILS = {
    "normal": "Standard travel pace. No mechanical benefits or penalties.",
    "forced march": "Forced March: Travel beyond 8 hours a day requires a Constitution saving throw at the end of each hour (starts at DC 10, increasing by +1 for each additional hour). On a failed save, a character suffers one level of Exhaustion.",
    "mounted": "Mounted Travel: Mounts do not increase daily travel distance. However, characters who do not meet Strength requirements for heavy armor suffer no speed penalty. Increased carrying capacity/encumbrance, and combat mobility advantages apply.",
    "gallop difficult terrain": "Gallop + Difficult Terrain: Mount speed is doubled for 1 hour per day, once per long rest. Difficult terrain cuts the total distance traveled per day in half.",
    "slow (sneak)": "Slow (Sneak) Pace: Allows characters to move stealthily. Grants Advantage on Wisdom (Perception) and Wisdom (Survival) checks.",
    "mounted difficult terrain": "Mounted + Difficult Terrain: Mounts do not increase daily travel distance. Difficult terrain cuts the total distance traveled per day in half.",
    "difficult terrain": "Difficult Terrain: Cuts the total distance traveled per day in half (doubles travel time).",
}


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
        travel_type = getattr(leg, "travel_type", "normal") or "normal"
        preset = TRAVEL_TYPES.get(travel_type, TRAVEL_TYPES["normal"])
        
        pace = preset["pace"]
        conveyance = preset["conveyance"]
        difficult_terrain = preset["difficult_terrain"]
        gallop = preset["gallop"]

        if pace not in self.paces:
            raise TravelError(f"unknown pace '{pace}'")
        conveyances = self.paces[pace]
        if conveyance not in conveyances:
            raise TravelError(f"unknown conveyance '{conveyance}'")
        if leg.terrain not in self.terrain:
            raise TravelError(f"unknown terrain '{leg.terrain}'")

        per_day = conveyances[conveyance] * self.terrain[leg.terrain]
        if per_day <= 0:  # pragma: no cover - a plugin would have to say 0 miles/day
            raise TravelError(f"'{leg.terrain}' is impassable by {conveyance}")

        if difficult_terrain:
            per_day *= 0.5

        # distance / (distance per travel-day) = travel-days, each `travel_day_seconds` long.
        duration = leg.distance / per_day * self.travel_day_seconds

        if gallop and conveyance == "horse":
            remaining_normal = duration
            actual = 0.0
            day_sec = self.travel_day_seconds
            while remaining_normal > 0:
                day_chunk = min(remaining_normal, day_sec)
                remaining_normal -= day_chunk
                actual += day_chunk - min(3600.0, day_chunk / 2.0)
            duration = actual

        return round(duration)


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

    # Detect if forced march preset is used in any leg, or request-level forced march is true
    forced_march = body.forced_march
    for leg in body.legs:
        if getattr(leg, "travel_type", "normal") == "forced march":
            forced_march = True

    legs: list[TravelLegOut] = []
    travel_seconds = 0
    for leg in body.legs:
        seconds = table.leg_seconds(leg)
        travel_seconds += seconds
        destination = session.get(Entity, leg.to_location_id) if leg.to_location_id else None
        # Every waypoint must belong to this campaign — otherwise a foreign
        # ``to_location_id`` would leak that entity's name into the response.
        if leg.to_location_id and (destination is None or destination.campaign_id != campaign.id):
            raise TravelError("waypoint location not found in this campaign")
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
    if not forced_march and per_day > 0 and overnight:
        rest_stops = max(0, (travel_seconds - 1) // per_day)
        rest_seconds = rest_stops * system.rest_duration_seconds(overnight)

    total = travel_seconds + rest_seconds
    cal = time_service.calendar_for(campaign)
    arrival = campaign.clock_time_game + total

    destination_id = body.legs[-1].to_location_id
    destination = session.get(Entity, destination_id) if destination_id else None
    if destination_id and (destination is None or destination.campaign_id != campaign.id):
        raise TravelError("destination not found in this campaign")

    # Forced-march Constitution saves accrue for each hour of travel beyond the
    # normal travel-day. RAW: the escalating exhaustion clock is *per day* (DC 10
    # +1 for each hour past the first 8), so it resets at each new day of travel
    # rather than climbing without bound across a multi-day march.
    forced_march_saves = []
    if forced_march:
        base_hours = max(1, table.travel_day_seconds // 3600)
        hours_per_day = 24
        total_hours = -(-travel_seconds // 3600)  # ceil to whole hours
        for h in range(1, total_hours + 1):
            hour_of_day = (h - 1) % hours_per_day + 1
            if hour_of_day > base_hours:
                forced_march_saves.append({
                    "hour": h,
                    "day": (h - 1) // hours_per_day + 1,
                    "dc": 10 + (hour_of_day - base_hours),
                })

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
        forced_march=forced_march,
        # What the GM most wants to see: the world does not wait for them.
        would_fire=time_service.preview_advance(
            session, campaign, delta_seconds=total
        ).would_fire,
        destination_id=destination_id,
        destination_name=destination.name if destination else None,
        forced_march_saves=forced_march_saves,
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
        if remaining > 0 and overnight and not preview.forced_march and more_rests:
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
                     "rest_stops": rests_taken, "forced_march": preview.forced_march},
            narrative=(
                f"The party traveled {_route(preview)}"
                f"{' by forced march' if preview.forced_march else ''}."
            ),
        )
        if preview.destination_id:
            party.current_location_id = preview.destination_id
            
            # Snap party marker coordinates if destination location is mapped
            map_id, x, y = resolve_location_coordinates(session, preview.destination_id)
            if map_id is not None:
                party.current_map_id = map_id
                party.current_x = x
                party.current_y = y
            else:
                party.current_map_id = None
                party.current_x = None
                party.current_y = None
                
            ctx.emit(
                "party_moved",
                payload={"to": preview.destination_id},
                narrative=f"The party arrived at {preview.destination_name}.",
                subject_entity_ids=(preview.destination_id,),
            )

        # Compile unique travel types and generate notification event
        travel_types = {getattr(leg, "travel_type", "normal") or "normal" for leg in preview.legs}
        rules_applied = []
        for tt in sorted(travel_types):
            desc = RULES_DETAILS.get(tt, RULES_DETAILS["normal"])
            rules_applied.append(f"- **{tt}**: {desc}")
            
        rules_description = "Special rules applied to the travel types used on this journey:\n\n" + "\n".join(rules_applied)
        
        from app.modules.time.models import ScheduledEvent
        from app.core.ids import new_id
        
        notification_event = ScheduledEvent(
            id=new_id(),
            campaign_id=campaign.id,
            fire_at_game=campaign.clock_time_game,
            title="Travel Rules Applied",
            description=rules_description,
            action_type="narrate",
            action_json="{}",
            status="fired",
            created_by_kind="gm"
        )
        session.add(notification_event)

    return TravelResult(
        from_time=from_time,
        to_time=campaign.clock_time_game,
        rest_stops=rests_taken,
        destination_id=preview.destination_id,
        destination_name=preview.destination_name,
        plan=preview,
    )


def resolve_location_coordinates(
    session: Session, location_id: str
) -> tuple[str | None, float | None, float | None]:
    """Helper to locate which map and coordinates represent a given location entity."""
    marker = session.scalars(
        select(MapMarker).where(MapMarker.target_entity_id == location_id)
    ).first()
    if marker:
        return marker.map_id, marker.x, marker.y
    region = session.scalars(
        select(MapRegion).where(MapRegion.target_entity_id == location_id)
    ).first()
    if region:
        try:
            poly = json.loads(region.polygon_json)
            if poly:
                xs = [p[0] for p in poly]
                ys = [p[1] for p in poly]
                return region.map_id, sum(xs) / len(poly), sum(ys) / len(poly)
        except Exception:
            pass
    return None, None, None
