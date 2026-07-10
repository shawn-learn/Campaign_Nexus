from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RuleSystemInfo(BaseModel):
    id: str
    name: str
    version: str
    sheet_types: list[str]


class ValidateRequest(BaseModel):
    sheet_type: str
    doc: dict[str, Any]


class ValidateResult(BaseModel):
    valid: bool
    errors: list[str]
    derived: dict[str, Any]


class StatBlockCreate(BaseModel):
    rule_system_id: str
    sheet_type: str
    label: str = Field(default="", max_length=200)
    doc: dict[str, Any] = {}


class StatBlockUpdate(BaseModel):
    label: str | None = None
    doc: dict[str, Any]


class StatBlockOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    campaign_id: str | None
    rule_system_id: str
    sheet_type: str
    schema_version: str
    label: str
    doc: dict[str, Any]
    derived: dict[str, Any]


class FacetDefOut(BaseModel):
    key: str
    label: str
    type: str


class ConditionOut(BaseModel):
    id: str
    name: str
    description: str


class MonsterFacets(BaseModel):
    facet1_num: float | None = None
    facet2_num: float | None = None
    facet1_text: str | None = None
    facet2_text: str | None = None


class MonsterOut(BaseModel):
    id: str
    name: str
    source: str
    variant_of: str | None
    rule_system_id: str
    sheet_type: str
    doc: dict[str, Any]
    derived: dict[str, Any]
    facets: MonsterFacets


class ImportResult(BaseModel):
    imported: int
