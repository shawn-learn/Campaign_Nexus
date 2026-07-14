from __future__ import annotations

import random
from typing import Any

from sqlalchemy.orm import Session

from app.core.pipeline import CommandContext
from app.modules.campaign import flags as campaign_flags
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
