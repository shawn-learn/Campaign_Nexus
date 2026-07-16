"""Export a whole campaign to JSON and import it back (as a new campaign).

Every id is remapped on import so an archive can be restored into the same database as a
duplicate. Built-in link types (campaign_id NULL) are shared and kept by id.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import now_real_iso
from app.core.domain_event import DomainEvent
from app.core.ids import new_id
from app.modules.atlas import service as atlas_service
from app.modules.atlas.models import Map, MapMarker, MapRegion, Media
from app.modules.campaign.models import Campaign, CampaignFlag
from app.modules.chronicle.models import Session as GameSession
from app.modules.chronicle.models import TimelineEntity, TimelineEntry
from app.modules.npcs.models import Npc, NpcLocationHistory, NpcSchedule
from app.modules.playbook.models import Encounter, Party, PartyMember, Quest
from app.modules.rules.models import Monster, StatBlock
from app.modules.story.models import StoryEdge, StoryNode
from app.modules.time.models import ScheduledEvent
from app.modules.wiki import search as wiki_search
from app.modules.wiki.models import Entity, EntityTag, Link, LinkType, Tag

# v2 embeds the Atlas: maps, markers, regions and the media bytes they point at (base64).
# A v1 archive (no ``media``/``maps`` keys) still imports — those sections just stay empty.
ARCHIVE_VERSION = 2


def _rows(session: Session, model: Any, campaign_id: str) -> list[Any]:
    return list(session.scalars(select(model).where(model.campaign_id == campaign_id)))


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def export_campaign(session: Session, campaign: Campaign) -> dict[str, Any]:
    cid = campaign.id

    def dump(obj: Any, fields: list[str]) -> dict[str, Any]:
        return {f: getattr(obj, f) for f in fields}

    entities = _rows(session, Entity, cid)
    parties = _rows(session, Party, cid)
    party_ids = [p.id for p in parties]

    return {
        "kind": "campaign",
        "version": ARCHIVE_VERSION,
        "exported_at": now_real_iso(),
        "campaign": {
            "name": campaign.name,
            "description": campaign.description,
            "rule_system_id": campaign.rule_system_id,
            "calendar_json": campaign.calendar_json,
            "clock_time_game": campaign.clock_time_game,
            "campaign_start_game": campaign.campaign_start_game,
            "settings_json": campaign.settings_json,
        },
        "link_types": [
            dump(lt, ["id", "label", "inverse_label", "is_semantic"])
            for lt in session.scalars(select(LinkType).where(LinkType.campaign_id == cid))
        ],
        "entities": [
            dump(e, ["id", "entity_type", "name", "slug", "summary", "article_json",
                     "article_text", "created_at_real", "updated_at_real", "deleted_at_real"])
            for e in entities
        ],
        "tags": [dump(t, ["id", "name", "color"]) for t in _rows(session, Tag, cid)],
        "entity_tags": [
            {"entity_id": et.entity_id, "tag_id": et.tag_id}
            for et in session.scalars(
                select(EntityTag)
                .join(Entity, Entity.id == EntityTag.entity_id)
                .where(Entity.campaign_id == cid)
            )
        ],
        "links": [
            dump(link, ["id", "from_entity", "to_entity", "link_type_id", "label", "notes",
                        "source", "valid_from_game", "valid_to_game", "created_at_real"])
            for link in _rows(session, Link, cid)
        ],
        "stat_blocks": [
            dump(sb, ["id", "rule_system_id", "sheet_type", "schema_version", "label",
                      "doc_json", "derived_json"])
            for sb in _rows(session, StatBlock, cid)
        ],
        "monsters": [
            dump(m, ["id", "name", "stat_block_id", "source", "variant_of",
                     "facet1_num", "facet2_num", "facet1_text", "facet2_text"])
            for m in _rows(session, Monster, cid)
        ],
        "parties": [
            dump(p, ["id", "current_location_id", "wealth_cp", "inventory_json", "reputation_json"])
            for p in parties
        ],
        "party_members": [
            {"party_id": pm.party_id, "stat_block_id": pm.stat_block_id, "name": pm.name,
             "status_json": pm.status_json, "active": bool(pm.active)}
            for pm in session.scalars(
                select(PartyMember).where(PartyMember.party_id.in_(party_ids))
            )
        ] if party_ids else [],
        "encounters": [
            dump(e, ["entity_id", "terrain", "hazards", "tactics", "combatants_json"])
            for e in _rows(session, Encounter, cid)
        ],
        "quests": [
            dump(q, ["entity_id", "quest_type", "status", "giver_npc_id", "rewards_json",
                     "deadline_game", "objectives_json"])
            for q in _rows(session, Quest, cid)
        ],
        "npcs": [
            dump(n, ["entity_id", "status", "current_location_id", "has_met_party",
                     "last_party_interaction_game", "goals", "secrets", "voice_notes",
                     "stat_block_id"])
            for n in _rows(session, Npc, cid)
        ],
        "npc_location_history": [
            dump(h, ["id", "npc_id", "location_id", "from_game", "to_game", "cause_event_id"])
            for h in _rows(session, NpcLocationHistory, cid)
        ],
        "npc_schedules": [
            dump(s, ["id", "npc_id", "label", "rule_json", "active",
                     "materialized_through_game"])
            for s in _rows(session, NpcSchedule, cid)
        ],
        "story_nodes": [
            dump(n, ["entity_id", "status", "pos_x", "pos_y", "consequences_json"])
            for n in _rows(session, StoryNode, cid)
        ],
        "story_edges": [
            dump(e, ["id", "from_node", "to_node", "condition_expr", "label"])
            for e in _rows(session, StoryEdge, cid)
        ],
        "scheduled_events": [
            dump(s, ["id", "fire_at_game", "recurrence_days", "action_type", "action_json",
                     "title", "created_by_kind", "source_entity_id", "status"])
            for s in _rows(session, ScheduledEvent, cid)
        ],
        "flags": [
            {"key": f.key, "value_json": f.value_json, "updated_at_game": f.updated_at_game,
             "updated_by_event": f.updated_by_event}
            for f in _rows(session, CampaignFlag, cid)
        ],
        "sessions": [
            dump(s, ["id", "session_number", "real_date", "status", "clock_start_game",
                     "clock_end_game", "summary"])
            for s in _rows(session, GameSession, cid)
        ],
        "events": [
            dump(ev, ["id", "seq", "event_type", "occurred_at_game", "recorded_at_real",
                      "session_id", "actor", "payload_json", "narrative_text",
                      "subject_entity_ids_json"])
            for ev in session.scalars(
                select(DomainEvent).where(DomainEvent.campaign_id == cid)
                .order_by(DomainEvent.seq)
            )
        ],
        "timeline": [
            dump(t, ["id", "event_id", "session_id", "occurred_at_game", "title", "body",
                     "icon", "significance", "is_hidden"])
            for t in _rows(session, TimelineEntry, cid)
        ],
        "timeline_entities": [
            {"timeline_id": te.timeline_id, "entity_id": te.entity_id}
            for te in session.scalars(
                select(TimelineEntity)
                .join(TimelineEntry, TimelineEntry.id == TimelineEntity.timeline_id)
                .where(TimelineEntry.campaign_id == cid)
            )
        ],
        # --- Atlas (v2): the map rows plus the image bytes they reference. ---------- #
        "media": _export_media(session, cid),
        "maps": [
            dump(m, ["entity_id", "media_id", "width_px", "height_px", "location_id",
                     "parent_map_id", "map_kind"])
            for m in _rows(session, Map, cid)
        ],
        "map_markers": [
            dump(mk, ["id", "map_id", "x", "y", "icon", "color", "note", "layer",
                      "target_entity_id", "child_map_id"])
            for mk in session.scalars(
                select(MapMarker)
                .join(Map, Map.entity_id == MapMarker.map_id)
                .where(Map.campaign_id == cid)
            )
        ],
        "map_regions": [
            dump(rg, ["id", "map_id", "name", "polygon_json", "color", "note", "layer",
                      "target_entity_id", "child_map_id"])
            for rg in session.scalars(
                select(MapRegion)
                .join(Map, Map.entity_id == MapRegion.map_id)
                .where(Map.campaign_id == cid)
            )
        ],
    }


def _export_media(session: Session, campaign_id: str) -> list[dict[str, Any]]:
    """Embed each media file's bytes as base64 so the archive is self-contained (FR-13.1)."""
    out: list[dict[str, Any]] = []
    for media in _rows(session, Media, campaign_id):
        path = atlas_service.media_abspath(media)
        if not path.exists():  # disk/db drift — skip rather than fail the whole export
            continue
        out.append({
            "id": media.id, "kind": media.kind, "filename": media.filename,
            "mime": media.mime, "bytes": media.bytes, "storage_path": media.storage_path,
            "created_at_real": media.created_at_real,
            "data_b64": base64.b64encode(path.read_bytes()).decode("ascii"),
        })
    return out


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #
class BadArchive(ValueError):
    pass


class _Remap:
    """Maps old ids to freshly-minted ones; built-in link types pass through."""

    def __init__(self) -> None:
        self._map: dict[str, str] = {}

    def new(self, old: str) -> str:
        if old not in self._map:
            self._map[old] = new_id()
        return self._map[old]

    def get(self, old: str | None) -> str | None:
        if old is None:
            return None
        return self._map.get(old)  # unmapped (e.g. built-in link type) -> None means "keep"

    def remap_json_ids(self, obj: Any) -> Any:
        """Deep-copy a JSON structure, replacing any string that is a *known old id*.

        Domain-event payloads carry entity ids as freeform values (``{"npc_id": …,
        "to": …}``), so a rebuild after import would replay them against dead ids unless we
        translate them here. A random string can't collide: only ids minted in this archive
        (UUIDv7) are keys in the map, so an unmapped string is left untouched."""
        if isinstance(obj, str):
            return self._map.get(obj, obj)
        if isinstance(obj, list):
            return [self.remap_json_ids(v) for v in obj]
        if isinstance(obj, dict):
            return {k: self.remap_json_ids(v) for k, v in obj.items()}
        return obj


def import_campaign(
    session: Session,
    archive: dict[str, Any],
    *,
    owner_user_id: str,
    name_override: str | None = None,
) -> Campaign:
    if archive.get("kind") != "campaign":
        raise BadArchive("not a campaign archive")

    r = _Remap()
    cdata = archive["campaign"]
    now = now_real_iso()
    campaign = Campaign(
        id=new_id(),
        name=name_override or f"{cdata['name']} (imported)",
        description=cdata.get("description"),
        rule_system_id=cdata["rule_system_id"],
        calendar_json=cdata.get("calendar_json", "{}"),
        clock_time_game=int(cdata.get("clock_time_game", 0)),
        campaign_start_game=int(cdata.get("campaign_start_game", 0)),
        settings_json=cdata.get("settings_json", "{}"),
        created_by=owner_user_id,
        created_at_real=now,
    )
    session.add(campaign)
    from app.modules.campaign.models import CampaignMember

    session.add(CampaignMember(campaign_id=campaign.id, user_id=owner_user_id, role="owner"))
    session.flush()

    def link_type_id(old: str) -> str:
        # Built-in link types are shared (kept); custom ones were remapped.
        return r.get(old) or old

    for lt in archive.get("link_types", []):
        session.add(LinkType(
            id=r.new(lt["id"]), campaign_id=campaign.id, label=lt["label"],
            inverse_label=lt["inverse_label"], is_semantic=bool(lt["is_semantic"]),
        ))

    imported_entities: list[Entity] = []
    for e in archive.get("entities", []):
        ent = Entity(
            id=r.new(e["id"]), campaign_id=campaign.id, entity_type=e["entity_type"],
            name=e["name"], slug=e["slug"], summary=e.get("summary"),
            article_json=e.get("article_json"), article_text=e.get("article_text"),
            created_by=owner_user_id,
            created_at_real=e.get("created_at_real", now),
            updated_at_real=e.get("updated_at_real", now),
            deleted_at_real=e.get("deleted_at_real"),
        )
        session.add(ent)
        imported_entities.append(ent)

    for t in archive.get("tags", []):
        session.add(Tag(id=r.new(t["id"]), campaign_id=campaign.id, name=t["name"],
                        color=t.get("color")))
    session.flush()
    for et in archive.get("entity_tags", []):
        session.add(EntityTag(entity_id=r.new(et["entity_id"]), tag_id=r.new(et["tag_id"])))

    for link in archive.get("links", []):
        session.add(Link(
            id=r.new(link["id"]), campaign_id=campaign.id,
            from_entity=r.new(link["from_entity"]), to_entity=r.new(link["to_entity"]),
            link_type_id=link_type_id(link["link_type_id"]), label=link.get("label"),
            notes=link.get("notes"), source=link.get("source", "explicit"),
            valid_from_game=link.get("valid_from_game"), valid_to_game=link.get("valid_to_game"),
            created_at_real=link.get("created_at_real", now),
        ))

    for sb in archive.get("stat_blocks", []):
        session.add(StatBlock(
            id=r.new(sb["id"]), campaign_id=campaign.id, rule_system_id=sb["rule_system_id"],
            sheet_type=sb["sheet_type"], schema_version=sb["schema_version"],
            label=sb.get("label", ""), doc_json=sb["doc_json"], derived_json=sb["derived_json"],
        ))
    session.flush()
    for m in archive.get("monsters", []):
        session.add(Monster(
            id=r.new(m["id"]), campaign_id=campaign.id, name=m["name"],
            stat_block_id=r.new(m["stat_block_id"]), source=m.get("source", "custom"),
            variant_of=r.get(m.get("variant_of")),
            facet1_num=m.get("facet1_num"), facet2_num=m.get("facet2_num"),
            facet1_text=m.get("facet1_text"), facet2_text=m.get("facet2_text"),
        ))

    for p in archive.get("parties", []):
        session.add(Party(
            id=r.new(p["id"]), campaign_id=campaign.id,
            current_location_id=r.get(p.get("current_location_id")),
            # Prefer copper; fall back to an older gp-only export.
            wealth_cp=int(p.get("wealth_cp", int(p.get("gold", 0)) * 100)),
            inventory_json=p.get("inventory_json", "[]"),
            reputation_json=p.get("reputation_json", "{}"),
        ))
    session.flush()
    for pm in archive.get("party_members", []):
        session.add(PartyMember(
            party_id=r.new(pm["party_id"]), stat_block_id=r.new(pm["stat_block_id"]),
            name=pm.get("name", ""), status_json=pm.get("status_json", "{}"),
            active=bool(pm.get("active", True)),
        ))

    for enc in archive.get("encounters", []):
        combatants = json.loads(enc.get("combatants_json", "[]"))
        for spec in combatants:
            spec["monster_id"] = r.get(spec.get("monster_id")) or spec.get("monster_id")
        session.add(Encounter(
            entity_id=r.new(enc["entity_id"]), campaign_id=campaign.id,
            terrain=enc.get("terrain"), hazards=enc.get("hazards"), tactics=enc.get("tactics"),
            combatants_json=json.dumps(combatants),
        ))

    for q in archive.get("quests", []):
        session.add(Quest(
            entity_id=r.new(q["entity_id"]), campaign_id=campaign.id,
            quest_type=q.get("quest_type", "side"), status=q.get("status", "unknown"),
            giver_npc_id=r.get(q.get("giver_npc_id")),
            rewards_json=q.get("rewards_json", "{}"), deadline_game=q.get("deadline_game"),
            objectives_json=q.get("objectives_json", "[]"),
        ))

    for n in archive.get("npcs", []):
        session.add(Npc(
            entity_id=r.new(n["entity_id"]), campaign_id=campaign.id,
            status=n.get("status", "alive"),
            current_location_id=r.get(n.get("current_location_id")),
            has_met_party=bool(n.get("has_met_party")),
            last_party_interaction_game=n.get("last_party_interaction_game"),
            goals=n.get("goals"), secrets=n.get("secrets"), voice_notes=n.get("voice_notes"),
            stat_block_id=r.get(n.get("stat_block_id")),
        ))
    for h in archive.get("npc_location_history", []):
        session.add(NpcLocationHistory(
            id=r.new(h["id"]), campaign_id=campaign.id, npc_id=r.new(h["npc_id"]),
            location_id=r.get(h.get("location_id")), from_game=h["from_game"],
            to_game=h.get("to_game"), cause_event_id=r.new(h["cause_event_id"]),
        ))
    for s in archive.get("npc_schedules", []):
        rule = json.loads(s.get("rule_json", "{}"))
        for stop in rule.get("stops", []):
            if stop.get("location_id"):
                stop["location_id"] = r.new(stop["location_id"])
        session.add(NpcSchedule(
            id=r.new(s["id"]), campaign_id=campaign.id, npc_id=r.new(s["npc_id"]),
            label=s.get("label", ""), rule_json=json.dumps(rule),
            active=bool(s.get("active", True)),
            materialized_through_game=s.get("materialized_through_game"),
        ))

    for n in archive.get("story_nodes", []):
        # Consequences embed quest/npc/location ids; remap them so a restored beat acts on
        # the imported entities, not the source's.
        cons = r.remap_json_ids(json.loads(n.get("consequences_json", "[]")))
        session.add(StoryNode(
            entity_id=r.new(n["entity_id"]), campaign_id=campaign.id,
            status=n.get("status", "possible"),
            pos_x=float(n.get("pos_x", 0.0)), pos_y=float(n.get("pos_y", 0.0)),
            consequences_json=json.dumps(cons),
        ))
    session.flush()
    for e in archive.get("story_edges", []):
        expr = e.get("condition_expr")
        if expr:  # ids appear as string literals inside the DSL; substitute the known ones
            for old, new in r._map.items():
                expr = expr.replace(old, new)
        session.add(StoryEdge(
            id=r.new(e["id"]), campaign_id=campaign.id,
            from_node=r.new(e["from_node"]), to_node=r.new(e["to_node"]),
            condition_expr=expr, label=e.get("label"),
        ))

    for s in archive.get("scheduled_events", []):
        action = json.loads(s.get("action_json", "{}"))
        # Actions carry entity ids in their payload; those must follow the remap too.
        for key in ("quest_id", "npc_id", "location_id", "schedule_id"):
            if action.get(key):
                action[key] = r.new(action[key])
        session.add(ScheduledEvent(
            id=r.new(s["id"]), campaign_id=campaign.id, fire_at_game=s["fire_at_game"],
            recurrence_days=s.get("recurrence_days"), action_type=s["action_type"],
            action_json=json.dumps(action), title=s["title"],
            created_by_kind=s.get("created_by_kind", "gm"),
            source_entity_id=r.get(s.get("source_entity_id")), status=s.get("status", "pending"),
        ))

    for s in archive.get("sessions", []):
        session.add(GameSession(
            id=r.new(s["id"]), campaign_id=campaign.id, session_number=s["session_number"],
            real_date=s.get("real_date"),
            status="completed" if s.get("status") == "live" else s.get("status", "planned"),
            clock_start_game=s.get("clock_start_game"), clock_end_game=s.get("clock_end_game"),
            summary=s.get("summary"),
        ))
    session.flush()

    for ev in archive.get("events", []):
        subjects = [r.new(x) for x in json.loads(ev.get("subject_entity_ids_json", "[]"))]
        # Entity ids embedded in the payload must follow the remap, so a rebuild-after-import
        # replays these events against the *imported* entities, not the source's dead ids.
        payload = r.remap_json_ids(json.loads(ev.get("payload_json", "{}")))
        session.add(DomainEvent(
            id=r.new(ev["id"]), campaign_id=campaign.id, seq=ev["seq"],
            event_type=ev["event_type"], occurred_at_game=ev["occurred_at_game"],
            recorded_at_real=ev.get("recorded_at_real", now),
            session_id=r.get(ev.get("session_id")), actor=ev.get("actor", "gm"),
            payload_json=json.dumps(payload), narrative_text=ev.get("narrative_text", ""),
            subject_entity_ids_json=json.dumps(subjects),
        ))

    for f in archive.get("flags", []):
        session.add(CampaignFlag(
            campaign_id=campaign.id, key=f["key"], value_json=f.get("value_json", "null"),
            updated_at_game=int(f.get("updated_at_game", 0)),
            updated_by_event=r.get(f.get("updated_by_event")),
        ))

    for t in archive.get("timeline", []):
        session.add(TimelineEntry(
            id=r.new(t["id"]), campaign_id=campaign.id, event_id=r.get(t.get("event_id")),
            session_id=r.get(t.get("session_id")), occurred_at_game=t["occurred_at_game"],
            title=t["title"], body=t.get("body"), icon=t.get("icon"),
            significance=int(t.get("significance", 2)), is_hidden=bool(t.get("is_hidden")),
        ))
    session.flush()
    for te in archive.get("timeline_entities", []):
        session.add(TimelineEntity(
            timeline_id=r.new(te["timeline_id"]), entity_id=r.new(te["entity_id"]),
        ))

    _import_media(session, archive, campaign.id, r)
    session.commit()

    # Rebuild the search index for the imported (non-deleted) entities.
    for ent in imported_entities:
        wiki_search.reindex(session, ent)
    session.commit()

    return campaign


def _import_media(
    session: Session, archive: dict[str, Any], campaign_id: str, r: _Remap
) -> None:
    """Recreate media files on disk (under the new campaign's dir) plus the Atlas rows.

    Content addressing means the bytes land at ``<campaign>/<sha256>.<ext>`` regardless of
    what path they had in the source campaign — so we re-derive the storage path from the
    bytes rather than trusting the archive's.
    """
    for m in archive.get("media", []):
        data = base64.b64decode(m["data_b64"])
        media = atlas_service.store_media_bytes(
            session, campaign_id, data,
            filename=m.get("filename", "media"), kind=m.get("kind", "map_image"),
            media_id=r.new(m["id"]),
        )
        # store_media_bytes re-sniffs; keep the archived created_at for provenance.
        media.created_at_real = m.get("created_at_real", media.created_at_real)

    for m in archive.get("maps", []):
        session.add(Map(
            entity_id=r.new(m["entity_id"]), campaign_id=campaign_id,
            media_id=r.new(m["media_id"]), width_px=m["width_px"], height_px=m["height_px"],
            location_id=r.get(m.get("location_id")),
            parent_map_id=r.get(m.get("parent_map_id")), map_kind=m.get("map_kind", "region"),
        ))
    session.flush()
    for mk in archive.get("map_markers", []):
        session.add(MapMarker(
            id=r.new(mk["id"]), map_id=r.new(mk["map_id"]), x=mk["x"], y=mk["y"],
            icon=mk.get("icon"), color=mk.get("color"), note=mk.get("note"),
            layer=mk.get("layer", "default"),
            target_entity_id=r.get(mk.get("target_entity_id")),
            child_map_id=r.get(mk.get("child_map_id")),
        ))
    for rg in archive.get("map_regions", []):
        session.add(MapRegion(
            id=r.new(rg["id"]), map_id=r.new(rg["map_id"]), name=rg.get("name"),
            polygon_json=rg["polygon_json"], color=rg.get("color"), note=rg.get("note"),
            layer=rg.get("layer", "default"),
            target_entity_id=r.get(rg.get("target_entity_id")),
            child_map_id=r.get(rg.get("child_map_id")),
        ))
