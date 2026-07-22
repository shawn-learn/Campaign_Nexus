"""Seed starting locations for the 13 Curse of Strahd NPCs in the database.

This backdates the relocation events to the start of the campaign (game clock = 0).
"""

from __future__ import annotations

import os
import sys

# Ensure backend root is in search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.db import SessionLocal
from app.core.pipeline import command_tx
from app.modules.campaign.models import Campaign
from app.modules.npcs.models import Npc
from app.modules.npcs.service import _name_of
from app.modules.wiki.models import Entity
from sqlalchemy import select

NPC_LOCATIONS = {
    # NPC name -> Location ID
    "Strahd von Zarovich": "019f51db-359e-7e2a-a2cc-7fab138a8605",  # Castle Ravenloft
    "Rahadin": "019f51db-359e-7e2a-a2cc-7fab138a8605",              # Castle Ravenloft
    "Izek Strazni": "019f53ae-8cf6-7899-b4f1-fea7c6267adc",         # N3. BURGOMASTER'S MANSION
    "Baba Lysaga": "019f51db-35d0-70ed-aab6-315f383b6cd4",          # The Ruins of Berez
    "Madam Eva": "019f51db-35fc-7c1b-81b8-2c079f06ef95",            # Tser Pool Encampment
    "Kasimir Velikov": "019f53b1-d5d2-78b2-941c-4281122c91d5",      # N9A. KASIMIR'S HOVEL
    "Ezmerelda d'Avenir": "019f51db-35d8-7568-84f9-5b570d5a23f3",   # Van Richten's Tower
    "Rudolph van Richten": "019f53ad-6f7a-7ac0-a705-7e8882b01f76",  # N2. BLUE WATER INN
    "The Abbot": "019f51db-35bb-7fb4-bd96-75612fed0e5f",            # Village of Krezk
    "Vladimir Horngaard": "019f53aa-8c1b-71e2-9490-08caa0789f13",   # Q36. DRAGON'S AUDIENCE HALL
    "Pidlwick II": "019f53b8-d0f3-7d23-9249-df3bc748c679",          # K59. HIGH TOWER PEAK
    "Ireena Kolyana": "019f51db-3597-7209-a3e9-cb1ac4824128",       # Village of Barovia
    "Patrina Velikovna": "019f53bb-6b03-7ac8-a309-f34096b237a3",    # K84. CATACOMBS
    "Lief Lipsiege": "019f53b6-e5a0-7d4f-99b9-f330cb53d9fb",         # K30. KING'S ACCOUNTANT
    "Cyrus Belview": "019f53b9-1068-7a42-ab3f-3cf68a90a8b5",         # K62. SERVANTS' HALL
    "Helga Ruvak": "019f53b7-2527-7683-ba65-c96781a0ee91",           # K32. MAID IN HELL
    "Sasha Ivliskova": "019f53bb-6b03-7ac8-a309-f34096b237a3",       # K84. CATACOMBS (Crypt 20)
    "Sir Klutz Tripalots": "019f53bb-6b03-7ac8-a309-f34096b237a3",   # K84. CATACOMBS (Crypt 33)
    "Prince Ariel du Plumette": "019f53bb-6b03-7ac8-a309-f34096b237a3", # K84. CATACOMBS (Crypt 4)
    "Khazan": "019f53bb-6b03-7ac8-a309-f34096b237a3",                 # K84. CATACOMBS (Crypt 15)
    "Sergei von Zarovich": "019f53bb-7ae5-7fea-a27f-59f19bfaa7e8",    # K85. SERGEI'S TOMB
    "King Barov von Zarovich": "019f53bb-aa66-7499-85ea-f74815266919", # K88. TOMB OF KING BAROV AND QUEEN RAVENOVIA
    "Queen Ravenovia van Roeyen": "019f53bb-aa66-7499-85ea-f74815266919", # K88. TOMB OF KING BAROV AND QUEEN RAVENOVIA
    "Artimus": "019f53bb-6b03-7ac8-a309-f34096b237a3",                # K84. CATACOMBS (Crypt 14)
    "Ludmilla Vilisevic": "019f53bb-8ab2-7407-a987-359b1501fcb9",     # K86. STRAHD'S TOMB
    "Anastasya Karelova": "019f53bb-8ab2-7407-a987-359b1501fcb9",     # K86. STRAHD'S TOMB
    "Volenta Popofsky": "019f53bb-8ab2-7407-a987-359b1501fcb9",       # K86. STRAHD'S TOMB
    "Gertruda": "019f53b7-c3a5-74b9-9eee-621da92e5561",               # K42. KING'S BEDCHAMBER
    "Escher": "019f53b8-3287-7b63-9226-831f82d8f79c",                 # K49. LOUNGE
}

def main():
    campaign_id = "019f51db-3552-7dd1-aba5-9180b3745bc5"  # Curse of Strahd
    with SessionLocal() as session:
        campaign = session.get(Campaign, campaign_id)
        if not campaign:
            print(f"Error: Campaign '{campaign_id}' not found.")
            sys.exit(1)

        print(f"Initializing NPC starting locations for campaign '{campaign.name}'...")

        for npc_name, loc_id in NPC_LOCATIONS.items():
            # Find the NPC entity
            npc_entity = session.scalar(
                select(Entity).where(
                    Entity.campaign_id == campaign_id,
                    Entity.entity_type == "npc",
                    Entity.name == npc_name
                )
            )
            if not npc_entity:
                print(f"Warning: NPC '{npc_name}' entity not found. Skipping.")
                continue

            npc = session.get(Npc, npc_entity.id)
            if not npc:
                print(f"Warning: NPC extension row for '{npc_name}' not found. Skipping.")
                continue

            if npc.current_location_id == loc_id:
                print(f" - {npc_name} is already at their starting location ({_name_of(session, loc_id)}).")
                continue

            from_name = _name_of(session, npc.current_location_id)
            to_name = _name_of(session, loc_id)
            print(f" - Moving {npc_name} from {from_name} to {to_name} at game start (clock=0)...")

            with command_tx(session, campaign_id, actor="gm") as ctx:
                # Custom emit to backdate the occurred_at_game to 0 (start of campaign)
                where = f"to {to_name}" if to_name else "out of sight"
                origin = f" from {from_name}" if from_name else ""
                ctx.emit(
                    "npc_relocated",
                    payload={"npc_id": npc.entity_id, "from": npc.current_location_id, "to": loc_id, "reason": "Start of campaign"},
                    narrative=f"{npc_name} traveled{origin} {where} (Start of campaign).",
                    occurred_at_game=0,
                    subject_entity_ids=(npc.entity_id,),
                )
        
        print("Done. Replaying and saving projections...")

if __name__ == "__main__":
    main()
