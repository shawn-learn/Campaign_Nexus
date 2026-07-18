"""Spell catalog service — list/get/create for the global spell reference."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.ids import new_id
from app.modules.spells.models import Spell
from app.modules.spells.schemas import SpellCreate, SpellOut


class SpellNotFound(LookupError):
    pass


def _out(spell: Spell) -> SpellOut:
    return SpellOut(
        id=spell.id, name=spell.name, source=spell.source, level=spell.level,
        school=spell.school, casting_time=spell.casting_time, range_text=spell.range_text,
        component_v=bool(spell.component_v), component_s=bool(spell.component_s),
        component_m=bool(spell.component_m), material=spell.material,
        concentration=bool(spell.concentration), ritual=bool(spell.ritual),
        classes=spell.classes, duration=spell.duration, description=spell.description,
        higher_levels=spell.higher_levels, damage_types=spell.damage_types,
        saving_throw=spell.saving_throw,
    )


def list_spells(
    session: Session, *,
    level: int | None = None,
    school: str | None = None,
    klass: str | None = None,
    source: str | None = None,
    q: str | None = None,
    limit: int = 2000,
) -> list[SpellOut]:
    stmt = select(Spell)
    if level is not None:
        stmt = stmt.where(Spell.level == level)
    if school:
        stmt = stmt.where(func.lower(Spell.school) == school.lower())
    if klass:
        stmt = stmt.where(Spell.classes.ilike(f"%{klass}%"))
    if source:
        stmt = stmt.where(func.lower(Spell.source) == source.lower())
    if q:
        stmt = stmt.where(Spell.name.ilike(f"%{q}%"))
    # Source breaks the tie: 379 names appear in both PHB and XPHB, so without it the two
    # printings of a spell come back in arbitrary order and look like a glitch.
    stmt = stmt.order_by(Spell.level, Spell.name, Spell.source).limit(limit)
    return [_out(s) for s in session.scalars(stmt)]


def spell_facets(session: Session) -> dict[str, list[str]]:
    """Distinct sources and class names present in the catalog, for filter dropdowns.

    A dedicated endpoint so the browser doesn't have to pull the whole catalog just to
    populate two ``<select>`` elements.
    """
    sources = sorted(
        s for s in session.scalars(select(Spell.source).distinct()) if s
    )
    classes: set[str] = set()
    for raw in session.scalars(select(Spell.classes).distinct()):
        for name in (raw or "").split(","):
            if name.strip():
                classes.add(name.strip())
    return {"sources": sources, "classes": sorted(classes)}


def get_spell(session: Session, spell_id: str) -> SpellOut:
    spell = session.get(Spell, spell_id)
    if spell is None:
        raise SpellNotFound(spell_id)
    return _out(spell)


def create_spell(session: Session, data: SpellCreate) -> SpellOut:
    """Create a spell, or return the existing one with the same ``(name, source)``.

    Idempotent so re-running the importer never duplicates — matches the bestiary /
    equipment-library seeding philosophy.
    """
    existing = session.scalars(
        select(Spell).where(Spell.name == data.name, Spell.source == data.source)
    ).first()
    if existing is not None:
        return _out(existing)
    spell = Spell(
        id=new_id(), name=data.name, source=data.source, level=data.level,
        school=data.school, casting_time=data.casting_time, range_text=data.range_text,
        component_v=data.component_v, component_s=data.component_s,
        component_m=data.component_m, material=data.material,
        concentration=data.concentration, ritual=data.ritual, classes=data.classes,
        duration=data.duration, description=data.description,
        higher_levels=data.higher_levels, damage_types=data.damage_types,
        saving_throw=data.saving_throw,
    )
    session.add(spell)
    session.commit()
    return _out(spell)
