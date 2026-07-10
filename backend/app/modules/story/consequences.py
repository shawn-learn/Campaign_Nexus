"""The closed catalog of story consequences (docs/11 §14.4, FR-4.3).

A consequence is *data*, not code: a dict ``{"action": <one of a fixed set>, ...params}``.
Each action maps to an existing command (set a flag, move a quest's status, relocate an NPC,
narrate) — so a story node can never do anything the GM couldn't do by hand, and campaign
data can never carry arbitrary behaviour. Applied in order when a node is activated.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.pipeline import command_tx
from app.modules.campaign import flags as campaign_flags
from app.modules.campaign.models import Campaign
from app.modules.npcs import service as npc_service
from app.modules.playbook import quests as quest_service

ACTIONS = ("set_flag", "activate_quest", "complete_quest", "fail_quest", "relocate_npc", "narrate")


class ConsequenceError(ValueError):
    pass


def validate(consequences: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reject anything outside the closed catalog or missing its required params."""
    clean: list[dict[str, Any]] = []
    for i, c in enumerate(consequences):
        if not isinstance(c, dict):
            raise ConsequenceError(f"consequence {i} is not an object")
        action = c.get("action")
        if action not in ACTIONS:
            raise ConsequenceError(f"consequence {i}: unknown action {action!r}")
        if action == "set_flag" and not c.get("key"):
            raise ConsequenceError(f"consequence {i}: set_flag needs a 'key'")
        if action in ("activate_quest", "complete_quest", "fail_quest") and not c.get("quest_id"):
            raise ConsequenceError(f"consequence {i}: {action} needs a 'quest_id'")
        if action == "relocate_npc" and not c.get("npc_id"):
            raise ConsequenceError(f"consequence {i}: relocate_npc needs an 'npc_id'")
        if action == "narrate" and not c.get("text"):
            raise ConsequenceError(f"consequence {i}: narrate needs 'text'")
        clean.append(c)
    return clean


_QUEST_TARGET = {"activate_quest": "active", "complete_quest": "completed", "fail_quest": "failed"}


def apply(session: Session, campaign: Campaign, consequences: list[dict[str, Any]]) -> list[str]:
    """Run each consequence, returning a human-readable log line per action.

    Each action delegates to the owning service (which manages its own transaction and
    events); a single bad step is logged and skipped rather than aborting the whole chain,
    so activating a node never half-applies then explodes.
    """
    log: list[str] = []
    for c in consequences:
        action = c["action"]
        try:
            if action == "set_flag":
                _set_flag(session, campaign, str(c["key"]), c.get("value", True))
                log.append(f"flag '{c['key']}' = {json.dumps(c.get('value', True))}")
            elif action in _QUEST_TARGET:
                quest_service.set_status(
                    session, campaign, str(c["quest_id"]), _QUEST_TARGET[action], actor="story"
                )
                log.append(f"{action.replace('_', ' ')} {c['quest_id']}")
            elif action == "relocate_npc":
                npc_service.relocate(
                    session, campaign, str(c["npc_id"]), c.get("location_id"),
                    reason="story consequence",
                )
                log.append(f"relocated npc {c['npc_id']}")
            elif action == "narrate":
                _narrate(session, campaign, str(c["text"]))
                log.append("narrated")
        except (quest_service.QuestError, npc_service.NpcError) as exc:
            log.append(f"skipped {action}: {exc}")
    return log


def _set_flag(session: Session, campaign: Campaign, key: str, value: Any) -> None:
    with command_tx(session, campaign.id, actor="story") as ctx:
        campaign_flags.set_flag(session, campaign.id, key, value, at_game=campaign.clock_time_game)
        ctx.emit(
            "flag_changed",
            payload={"key": key, "value": value, "source": "story"},
            narrative=f"Flag '{key}' set to {json.dumps(value)}.",
        )


def _narrate(session: Session, campaign: Campaign, text: str) -> None:
    with command_tx(session, campaign.id, actor="story") as ctx:
        ctx.emit("world_event", payload={"source": "story"}, narrative=text)
