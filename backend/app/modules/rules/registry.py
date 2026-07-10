"""Rule-system registry — the single place plugins are wired in (docs/08, §10.2).

Other modules resolve systems through this registry, never by importing plugin packages
directly (import-linter enforced). ``sync_rule_systems`` mirrors installed plugins into the
``rule_system`` catalog table so campaigns can reference them by id.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.campaign.models import RuleSystem as RuleSystemRow
from app.modules.rules.interface import RuleSystem
from app.modules.rules.systems.dnd5e import SYSTEM as DND5E
from app.modules.rules.systems.nimble import SYSTEM as NIMBLE
from app.modules.rules.systems.simpletest import SYSTEM as SIMPLETEST

# Built-in systems. This module is the *only* one allowed to import a plugin package (§10.8).
_SYSTEMS: dict[str, RuleSystem] = {
    DND5E.id: DND5E,
    NIMBLE.id: NIMBLE,
    SIMPLETEST.id: SIMPLETEST,
}


class UnknownRuleSystem(KeyError):
    pass


def all_systems() -> list[RuleSystem]:
    return list(_SYSTEMS.values())


def get_system(system_id: str) -> RuleSystem:
    try:
        return _SYSTEMS[system_id]
    except KeyError as exc:
        raise UnknownRuleSystem(system_id) from exc


def has_system(system_id: str) -> bool:
    return system_id in _SYSTEMS


def sync_rule_systems(session: Session) -> None:
    """Upsert a catalog row per installed plugin (idempotent; safe at startup)."""
    for system in _SYSTEMS.values():
        row = session.get(RuleSystemRow, system.id)
        if row is None:
            session.add(
                RuleSystemRow(id=system.id, name=system.name, version=system.version, enabled=True)
            )
        else:
            row.name = system.name
            row.version = system.version
    session.commit()
