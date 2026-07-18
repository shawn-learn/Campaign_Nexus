"""Spell catalog: a global reference table plus the 5etools converter that fills it.

The catalog is campaign-independent (like the equipment library), keyed logically by
``(name, source)`` — the same spell genuinely appears in more than one book, and the 2024
rules changed some of them, so both printings must coexist.
"""

from __future__ import annotations

from app.modules.import5e import spells as spell_import
from fastapi.testclient import TestClient


def _spell(**overrides) -> dict:
    body = {"name": "Test Bolt", "source": "PHB", "level": 3, "school": "Evocation",
            "casting_time": "1 action", "range_text": "120 feet",
            "component_v": True, "component_s": True, "classes": "Wizard, Sorcerer"}
    body.update(overrides)
    return body


def _create(client: TestClient, **overrides):
    return client.post("/api/v1/spells", json=_spell(**overrides))


# --------------------------------------------------------------------------- #
# create / get
# --------------------------------------------------------------------------- #
def test_create_and_fetch_a_spell(client: TestClient) -> None:
    created = _create(client)
    assert created.status_code == 201, created.text
    spell = created.json()
    assert spell["name"] == "Test Bolt" and spell["level"] == 3
    assert spell["component_v"] is True and spell["component_m"] is False

    fetched = client.get(f"/api/v1/spells/{spell['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == spell


def test_create_is_idempotent_per_name_and_source(client: TestClient) -> None:
    """Re-running the importer must not duplicate — same rule as bestiary seeding."""
    first = _create(client).json()
    second = _create(client).json()
    assert first["id"] == second["id"]
    assert len(client.get("/api/v1/spells?q=Test Bolt").json()) == 1


def test_same_name_in_a_different_source_is_a_separate_spell(client: TestClient) -> None:
    """379 real spell names appear in both PHB and XPHB, and the 2024 rules changed some
    of them (Acid Splash moved from Conjuration to Evocation), so both must be kept."""
    phb = _create(client, source="PHB", school="Conjuration").json()
    xphb = _create(client, source="XPHB", school="Evocation").json()
    assert phb["id"] != xphb["id"]
    names = client.get("/api/v1/spells?q=Test Bolt").json()
    assert [s["source"] for s in names] == ["PHB", "XPHB"]  # ordered, not arbitrary


def test_missing_spell_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/spells/nope").status_code == 404


# --------------------------------------------------------------------------- #
# filters
# --------------------------------------------------------------------------- #
def test_filters_narrow_the_list(client: TestClient) -> None:
    _create(client, name="Alpha", level=1, school="Abjuration", classes="Cleric")
    _create(client, name="Beta", level=3, school="Evocation", classes="Wizard")
    _create(client, name="Gamma", level=3, school="Evocation", classes="Wizard, Bard",
            source="XGE")

    def names(query: str) -> list[str]:
        return [s["name"] for s in client.get(f"/api/v1/spells?{query}").json()]

    assert names("level=3") == ["Beta", "Gamma"]
    assert names("school=Abjuration") == ["Alpha"]
    assert names("school=evocation") == ["Beta", "Gamma"]     # case-insensitive
    assert names("class=Bard") == ["Gamma"]
    assert names("source=XGE") == ["Gamma"]
    assert names("q=amm") == ["Gamma"]                         # substring match
    assert names("level=3&class=Wizard&source=PHB") == ["Beta"]


def test_list_is_ordered_by_level_then_name(client: TestClient) -> None:
    _create(client, name="Zeta", level=1)
    _create(client, name="Alpha", level=5)
    _create(client, name="Beta", level=1)
    listed = [(s["level"], s["name"]) for s in client.get("/api/v1/spells").json()]
    assert listed == sorted(listed)


def test_limit_is_honoured(client: TestClient) -> None:
    for n in range(5):
        _create(client, name=f"Spell {n}", level=n)
    assert len(client.get("/api/v1/spells?limit=2").json()) == 2


# --------------------------------------------------------------------------- #
# facets
# --------------------------------------------------------------------------- #
def test_facets_report_sources_and_split_classes(client: TestClient) -> None:
    """`classes` is a comma-separated string; the facet must split it, not echo it."""
    _create(client, name="Alpha", source="PHB", classes="Wizard, Sorcerer")
    _create(client, name="Beta", source="XGE", classes="Bard,Wizard")

    facets = client.get("/api/v1/spells/facets").json()
    assert facets["sources"] == ["PHB", "XGE"]
    assert facets["classes"] == ["Bard", "Sorcerer", "Wizard"]


def test_facets_route_is_not_shadowed_by_the_id_route(client: TestClient) -> None:
    """`/facets` must win over `/{spell_id}`, which would otherwise 404 it."""
    assert client.get("/api/v1/spells/facets").status_code == 200


# --------------------------------------------------------------------------- #
# 5etools converter
# --------------------------------------------------------------------------- #
#: Shape-representative, own wording — no book text is committed.
FIREBOLT = {
    "name": "Test Bolt", "source": "PHB", "level": 3, "school": "V",
    "time": [{"number": 1, "unit": "action"}],
    "range": {"type": "point", "distance": {"type": "feet", "amount": 120}},
    "components": {"v": True, "s": True, "m": "a pinch of soot"},
    "duration": [{"type": "instant"}],
    "entries": ["A streak of flame deals {@damage 8d6} fire damage."],
    "entriesHigherLevel": [{"type": "entries", "name": "At Higher Levels",
                            "entries": ["Deals {@scaledamage 8d6|3-9|1d6} more."]}],
    "damageInflict": ["fire"], "savingThrow": ["dexterity"],
}


def test_converter_maps_a_spell_entry():
    doc = spell_import.to_spell(FIREBOLT)
    assert doc is not None
    assert doc["name"] == "Test Bolt" and doc["level"] == 3
    assert doc["school"] == "Evocation"          # "V" is the school code
    assert doc["casting_time"] == "1 action"
    assert doc["range_text"] == "120 feet"
    assert (doc["component_v"], doc["component_s"], doc["component_m"]) == (True, True, True)
    assert doc["material"] == "a pinch of soot"
    assert doc["damage_types"] == "fire"
    assert doc["saving_throw"] == "dexterity"
    assert "{@" not in doc["description"]        # inline tags stripped


def test_converted_spell_is_accepted_by_the_api(client: TestClient) -> None:
    """The load-bearing check: the converter's output satisfies SpellCreate."""
    doc = spell_import.to_spell(FIREBOLT)
    created = client.post("/api/v1/spells", json=doc)
    assert created.status_code == 201, created.text
    assert created.json()["school"] == "Evocation"


def test_converter_joins_the_class_list():
    doc = spell_import.to_spell(FIREBOLT, classes=["Wizard", "Sorcerer"])
    assert doc["classes"] == "Wizard, Sorcerer"
    assert spell_import.to_spell(FIREBOLT)["classes"] is None


def test_class_map_inverts_the_sources_file():
    """`spells/sources.json` is keyed source -> spell -> class list; the importer needs
    the inverse, keyed by (spell, source)."""
    sources = {"PHB": {"Test Bolt": {"class": [{"name": "Wizard"}, {"name": "Sorcerer"}]}}}
    assert spell_import.load_class_map(sources) == {("Test Bolt", "PHB"): ["Sorcerer", "Wizard"]}


def test_converter_skips_entries_without_a_name_or_level():
    assert spell_import.to_spell({"level": 1}) is None
    assert spell_import.to_spell({"name": "No Level"}) is None
