from __future__ import annotations

import json
import random
from typing import Any

from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.core.event_bus import EventRecord, event_bus
from app.core.ids import new_id
from app.core.pipeline import CommandContext
from app.modules.campaign import flags as campaign_flags
from app.modules.campaign.models import Campaign
from app.modules.time import scheduled
from app.modules.time.models import ScheduledEvent

# Custom Action Type for Barovian Weather and Mist updates.
WEATHER_ACTION = "cos_weather_roll"

def roll_weather(
    session: Session,
    ctx: CommandContext,
    campaign_id: str,
    at_time: int,
    scheduled_event_id: str | None = None,
) -> dict[str, Any]:
    # 1. Roll Temperature (d20) - reference: cos/rolls.md
    t_roll = random.randint(1, 20)
    if t_roll <= 14:
        temp_desc = "normal for the season (chilly)"
        temp_c = 5  # chilly normal
    elif t_roll <= 17:
        diff = random.randint(1, 6)
        temp_desc = f"{diff}°C colder than normal"
        temp_c = 5 - diff
    else:
        diff = random.randint(1, 6)
        temp_desc = f"{diff}°C hotter than normal"
        temp_c = 5 + diff

    # 2. Roll Wind (d20) - reference: cos/rolls.md
    w_roll = random.randint(1, 20)
    if w_roll <= 12:
        wind = "None"
        wind_desc = "calm skies"
    elif w_roll <= 17:
        wind = "Light"
        wind_desc = "a light breeze"
    else:
        wind = "Strong"
        wind_desc = "strong, howling winds (imposes disadvantage on ranged attacks and hearing Perception)"

    # 3. Roll Precipitation (d20) - reference: cos/rolls.md
    p_roll = random.randint(1, 20)
    if p_roll <= 12:
        precip = "None"
        precip_desc = "no rain or snow"
    elif p_roll <= 17:
        precip = "Light rain/snow"
        precip_desc = "light rain/drizzle"
    else:
        precip = "Heavy rain/snow"
        precip_desc = "heavy precipitation (imposes disadvantage on sight/hearing Perception)"

    # 4. Roll Mist Thickness (d20) - reference: cos/rolls.md
    m_roll = random.randint(1, 20)
    if m_roll <= 1:
        mist = "None"
        mist_desc = "a rare clear day in Barovia (can see across the valley)"
    elif m_roll <= 14:
        mist = "Light"
        mist_desc = "light fog (visibility limited to 120 feet)"
    elif m_roll <= 19:
        mist = "Heavy"
        mist_desc = "heavy fog (visibility limited to 60 feet)"
    else:
        mist = "Choking"
        mist_desc = "choking mist (essentially 0 visibility, sight-based attacks have disadvantage)"

    # Update campaign flags
    campaign_flags.set_flag(session, campaign_id, "weather_temperature_c", temp_c, at_game=at_time)
    campaign_flags.set_flag(session, campaign_id, "weather_wind", wind, at_game=at_time)
    campaign_flags.set_flag(session, campaign_id, "weather_precipitation", precip, at_game=at_time)
    campaign_flags.set_flag(session, campaign_id, "weather_mist_thickness", mist, at_game=at_time)

    narrative = f"Weather Update: {mist_desc}, {wind_desc}, {precip_desc}. Temp: {temp_desc} ({temp_c}°C)."
    
    ctx.emit(
        "world_event",
        payload={
            "title": "Barovian Weather Change",
            "scheduled_event_id": scheduled_event_id,
            "temperature_c": temp_c,
            "wind": wind,
            "precipitation": precip,
            "mist": mist
        },
        narrative=narrative,
        occurred_at_game=at_time,
    )
    return {
        "narrative": narrative,
        "temperature_c": temp_c,
        "wind": wind,
        "precipitation": precip,
        "mist": mist,
        "occurred_at_game": at_time
    }

def _weather_execute(
    session: Session,
    ctx: CommandContext,
    campaign_id: str,
    event: ScheduledEvent,
    action: dict[str, Any],
    at_time: int,
) -> str:
    res = roll_weather(session, ctx, campaign_id, at_time, scheduled_event_id=event.id)
    return str(res["narrative"])

def _weather_describe(event: ScheduledEvent, action: dict[str, Any]) -> str:
    return "Roll weather and mist thickness in Barovia and update campaign flags."

# Register action handler
scheduled.register_action(WEATHER_ACTION, execute=_weather_execute, describe=_weather_describe)


# Custom Action Type for Barovian Full Moon
FULL_MOON_ACTION = "cos_full_moon"


def _full_moon_execute(
    session: Session,
    ctx: CommandContext,
    campaign_id: str,
    event: ScheduledEvent,
    action: dict[str, Any],
    at_time: int,
) -> str:
    # 1. Set the is_full_moon campaign flag to True
    campaign_flags.set_flag(session, campaign_id, "is_full_moon", True, at_game=at_time)

    # 2. Schedule a one-shot set_flag event to clear it at dawn (10 hours later, 6 AM)
    # 10 hours * 3600 seconds/hour = 36000 seconds
    clear_time = at_time + 10 * 3600

    scheduled.schedule_for_source(
        session,
        campaign_id,
        source_entity_id="cos_full_moon_tracker",
        action_type="set_flag",
        action={"key": "is_full_moon", "value": False},
        fire_at_game=clear_time,
        title="Full Moon Ends",
        created_by_kind="system",
        description="End of the full moon phase, clearing the is_full_moon flag."
    )

    narrative = "The full moon rises over Barovia. A silver light bathes the valley, and howls echo in the distance."

    ctx.emit(
        "world_event",
        payload={
            "title": "Full Moon Rises",
            "scheduled_event_id": event.id,
        },
        narrative=narrative,
        occurred_at_game=at_time,
    )
    return narrative


def _full_moon_describe(event: ScheduledEvent, action: dict[str, Any]) -> str:
    return "The full moon rises: sets is_full_moon=True and schedules clearing flag at dawn."


# Register action handler for full moon
scheduled.register_action(FULL_MOON_ACTION, execute=_full_moon_execute, describe=_full_moon_describe)


# Event Bus subscriber to auto-schedule the full moon event on campaign creation
def _on_campaign_created(event: EventRecord) -> None:
    if event.event_type == "campaign_created":
        with SessionLocal() as session:
            campaign = session.get(Campaign, event.campaign_id)
            if campaign:
                try:
                    calendar = json.loads(campaign.calendar_json)
                except (json.JSONDecodeError, TypeError):
                    return
                if calendar.get("id") == "barovian":
                    from sqlalchemy import select
                    exists = session.scalar(
                        select(ScheduledEvent).where(
                            ScheduledEvent.campaign_id == campaign.id,
                            ScheduledEvent.action_type == FULL_MOON_ACTION
                        )
                    )
                    if not exists:
                        # Full moon is on the 15th night (index 14) of the first month (Lunas, index 0)
                        # rise at 8:00 PM (20:00)
                        # 14 days * 24 hours/day * 3600 seconds/hour + 20 hours * 3600 seconds/hour
                        # = 1209600 + 72000 = 1281600 seconds
                        first_full_moon_seconds = 14 * 24 * 3600 + 20 * 3600
                        fm_event = ScheduledEvent(
                            id=new_id(),
                            campaign_id=campaign.id,
                            fire_at_game=first_full_moon_seconds,
                            recurrence_days=30,  # Each Barovian month has exactly 30 days
                            action_type=FULL_MOON_ACTION,
                            action_json="{}",
                            title="Full Moon",
                            created_by_kind="system",
                            description="The monthly full moon rises, bathing Barovia in light and triggering werewolf activity.",
                            status="pending",
                        )
                        session.add(fm_event)
                        session.commit()


# Subscribe to campaign created events
event_bus.subscribe(_on_campaign_created)


