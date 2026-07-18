from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.modules.spells import service
from app.modules.spells.schemas import SpellCreate, SpellFacetsOut, SpellOut

# Global (spell reference is not campaign-specific), like the equipment library.
router = APIRouter(prefix="/api/v1/spells", tags=["spells"])


@router.get("", response_model=list[SpellOut])
def list_spells(
    level: int | None = Query(default=None, ge=0, le=9),
    school: str | None = Query(default=None),
    klass: str | None = Query(default=None, alias="class"),
    source: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=2000, ge=1, le=100000),
    session: Session = Depends(get_session),
) -> list[SpellOut]:
    return service.list_spells(
        session, level=level, school=school, klass=klass, source=source, q=q, limit=limit
    )


# Declared before "/{spell_id}" so the literal path wins the route match.
@router.get("/facets", response_model=SpellFacetsOut)
def spell_facets(session: Session = Depends(get_session)) -> SpellFacetsOut:
    return SpellFacetsOut(**service.spell_facets(session))


@router.post("", response_model=SpellOut, status_code=status.HTTP_201_CREATED)
def create_spell(
    body: SpellCreate,
    session: Session = Depends(get_session),
) -> SpellOut:
    return service.create_spell(session, body)


@router.get("/{spell_id}", response_model=SpellOut)
def get_spell(
    spell_id: str,
    session: Session = Depends(get_session),
) -> SpellOut:
    try:
        return service.get_spell(session, spell_id)
    except service.SpellNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "spell not found") from exc
