"""Seed campaign images (portraits, stat blocks, treasures, and handouts) to the database.

Walks the Images folder and links them to matching entities or notes.
"""

from __future__ import annotations

import os
import sys

# Ensure backend root is in search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.clock import now_real_iso
from app.core.db import SessionLocal
from app.core.ids import new_id
from app.modules.atlas.models import EntityMedia
from app.modules.atlas.service import store_media_bytes
from app.modules.campaign.models import Campaign
from app.modules.wiki.models import Entity
from sqlalchemy import func, select

# Mapping of filename -> (entity_type, entity_name, caption)
MAPPING = {
    # NPCs
    "Baba Lysaga.png": ("npc", "Baba Lysaga", "Baba Lysaga portrait"),
    "Baba Lysaga Stat Block.png": ("npc", "Baba Lysaga", "Baba Lysaga stat block"),
    "Ezmerelda.jpg": ("npc", "Ezmerelda d'Avenir", "Ezmerelda d'Avenir portrait"),
    "Ezmerelda Stat Block.png": ("npc", "Ezmerelda d'Avenir", "Ezmerelda d'Avenir stat block"),
    "Ireena Kolyana.png": ("npc", "Ireena Kolyana", "Ireena Kolyana portrait"),
    "Izek.jpg": ("npc", "Izek Strazni", "Izek Strazni portrait"),
    "Izek Stat Block.png": ("npc", "Izek Strazni", "Izek Strazni stat block"),
    "Kasimir.jpg": ("npc", "Kasimir Velikov", "Kasimir Velikov portrait"),
    "Madam Eva Stat Block.png": ("npc", "Madam Eva", "Madam Eva stat block"),
    "Pidlwick II.jpg": ("npc", "Pidlwick II", "Pidlwick II portrait"),
    "Pidlwick II Stat Block.png": ("npc", "Pidlwick II", "Pidlwick II stat block"),
    "Rahadin.jpg": ("npc", "Rahadin", "Rahadin portrait"),
    "Rahadin's Stat Block.png": ("npc", "Rahadin", "Rahadin stat block"),
    "Rictavio.png": ("npc", "Rudolph van Richten", "Rictavio (Rudolph van Richten) portrait"),
    "Rictavio Stat Block.png": ("npc", "Rudolph van Richten", "Rudolph van Richten stat block"),
    "Strahd Stat Block.png": ("npc", "Strahd von Zarovich", "Strahd von Zarovich stat block"),
    "Strahd's Crest.png": ("npc", "Strahd von Zarovich", "Strahd's Crest"),
    "Strahd Portrait.png": ("npc", "Strahd von Zarovich", "Strahd von Zarovich portrait"),
    "Portrait of Strahd.jpg": ("npc", "Strahd von Zarovich", "Strahd von Zarovich portrait"),
    "The Abbot Stat Block.png": ("npc", "The Abbot", "The Abbot stat block"),
    "Vladimir Horngaard.png": ("npc", "Vladimir Horngaard", "Vladimir Horngaard portrait"),
    
    # Monsters
    "Baba Lysaga's Creeping Hut Stat Block.png": ("monster", "Baba Lysaga's Creeping Hut", "Baba Lysaga's Creeping Hut stat block"),
    "Barovian Witch.png": ("monster", "Barovian Witch", "Barovian Witch illustration"),
    "Barovian Witch Stat Block.png": ("monster", "Barovian Witch", "Barovian Witch stat block"),
    "Broom of Animated Attack Stat Block.png": ("monster", "Broom of Animated Attack", "Broom of Animated Attack stat block"),
    "Guardian Portrait Stat Block.png": ("monster", "Guardian Portrait", "Guardian Portrait stat block"),
    "Mongrelfolk Stat Block.png": ("monster", "Mongrelfolk", "Mongrelfolk stat block"),
    "Phantom Warrior.jpg": ("monster", "Phantom Warrior", "Phantom Warrior illustration"),
    "Phantom Warrior Stat Block.png": ("monster", "Phantom Warrior", "Phantom Warrior stat block"),
    "Strahd Zombie Stat Block.png": ("monster", "Strahd Zombie", "Strahd Zombie stat block"),
    "Strahd's Animated Armor.jpg": ("monster", "Strahd's Animated Armor", "Strahd's Animated Armor illustration"),
    "Strahd's Animated Armor Stat Block.png": ("monster", "Strahd's Animated Armor", "Strahd's Animated Armor stat block"),
    "Tree Blight Stat Block.png": ("monster", "Tree Blight", "Tree Blight stat block"),
    "Wereraven Stat Block.png": ("monster", "Wereraven", "Wereraven stat block"),

    # Quests / Treasures
    "Sunsword.PNG": ("quest", "Retrieve the Sunsword", "The Sunsword"),
    "Tome of Strahd.png": ("quest", "Recover the Tome of Strahd", "The Tome of Strahd"),
    "Holy Symbol of Ravenkind.jpg": ("quest", "Find the Holy Symbol of Ravenkind", "The Holy Symbol of Ravenkind"),

    # Notes - Character Options
    "Character Personality Bonds and Flaws Random Table.png": ("note", "Appendix A: Character Options", "Bonds and Flaws Random Table"),
    "Character Personality Traits and Ideals Random Table.png": ("note", "Appendix A: Character Options", "Traits and Ideals Random Table"),
    "Gothic Trinkets Pt. 1.png": ("note", "Appendix A: Character Options", "Gothic Trinkets Pt. 1"),
    "Gothic Trinkets Pt. 2.png": ("note", "Appendix A: Character Options", "Gothic Trinkets Pt. 2"),
    "Gothic Trinkets Pt. 3.png": ("note", "Appendix A: Character Options", "Gothic Trinkets Pt. 3"),
    "Harrowing Event Character Background Random Table.png": ("note", "Appendix A: Character Options", "Harrowing Event Random Table"),
    
    # Notes - Treasures
    "Blood Spear.png": ("note", "Appendix C: Treasures", "Blood Spear"),
    "Gulthias Staff.png": ("note", "Appendix C: Treasures", "Gulthias Staff"),
    "Icon of Ravenloft.png": ("note", "Appendix C: Treasures", "Icon of Ravenloft"),
    "St. Markovia's Thighbone.png": ("note", "Appendix C: Treasures", "Saint Markovia's Thighbone"),
    
    # Notes - Tarokka Deck
    "Tarokka High Deck.png": ("note", "Appendix E: The Tarokka Deck", "Tarokka High Deck"),
    "Tarokka Swords.png": ("note", "Appendix E: The Tarokka Deck", "Tarokka Swords"),
    "Tarokka Stars.png": ("note", "Appendix E: The Tarokka Deck", "Tarokka Stars"),
    "Tarokka Coins.png": ("note", "Appendix E: The Tarokka Deck", "Tarokka Coins"),
    "Tarokka Glyphs.png": ("note", "Appendix E: The Tarokka Deck", "Tarokka Glyphs"),
    "Tarokka Deck 1.png": ("note", "Appendix E: The Tarokka Deck", "Tarokka Deck 1"),
    "Tarokka Deck 2.png": ("note", "Appendix E: The Tarokka Deck", "Tarokka Deck 2"),
    "Tarokka Deck 3.png": ("note", "Appendix E: The Tarokka Deck", "Tarokka Deck 3"),
    "Tarokka Deck 4.png": ("note", "Appendix E: The Tarokka Deck", "Tarokka Deck 4"),
    "Tarokka Deck 5.png": ("note", "Appendix E: The Tarokka Deck", "Tarokka Deck 5"),
    "Tarokka Deck 6.png": ("note", "Appendix E: The Tarokka Deck", "Tarokka Deck 6"),
    
    # Notes - Handouts
    "Kolyan Indirovich's Letter (Version 1).png": ("note", "Appendix F: Handouts", "Kolyan Indirovich's Letter (Version 1)"),
    "Strahd's Invitation.png": ("note", "Appendix F: Handouts", "Strahd's Invitation"),
    "From the Tome of Strahd.png": ("note", "Appendix F: Handouts", "From the Tome of Strahd (Page 1)"),
    "From the Tome of Strahd 2.png": ("note", "Appendix F: Handouts", "From the Tome of Strahd (Page 2)"),
    "Journal of Rudolph van Richten.png": ("note", "Appendix F: Handouts", "Journal of Rudolph van Richten (Page 1)"),
    "Journal of Rudolph van Richten 2.png": ("note", "Appendix F: Handouts", "Journal of Rudolph van Richten (Page 2)"),
    "Kolyan Indirovich's Letter (Version 2).png": ("note", "Appendix F: Handouts", "Kolyan Indirovich's Letter (Version 2)"),
    "Journal of Argynvost.png": ("note", "Appendix F: Handouts", "Journal of Argynvost"),
}

def main():
    campaign_id = "019f51db-3552-7dd1-aba5-9180b3745bc5"  # Curse of Strahd
    images_dir = r"c:\GitHub\Campaign_Nexus\Curse of Strahd\Images"
    
    with SessionLocal() as session:
        campaign = session.get(Campaign, campaign_id)
        if not campaign:
            print(f"Error: Campaign '{campaign_id}' not found.")
            sys.exit(1)
            
        print(f"Scanning and seeding images for '{campaign.name}'...")
        
        # Build dictionary of files in images_dir (case-insensitive keys for easy lookup)
        found_files = {}
        for root, _, files in os.walk(images_dir):
            for file in files:
                found_files[file.lower()] = os.path.join(root, file)
                
        for filename, (etype, ename, caption) in MAPPING.items():
            lower_name = filename.lower()
            if lower_name not in found_files:
                print(f" - Warning: File '{filename}' not found on disk. Skipping.")
                continue
                
            filepath = found_files[lower_name]
            
            # Find the entity
            entity = session.scalar(
                select(Entity).where(
                    Entity.campaign_id == campaign_id,
                    Entity.entity_type == etype,
                    Entity.name == ename
                )
            )
            if not entity:
                print(f" - Warning: Target {etype} '{ename}' not found in DB. Skipping '{filename}'.")
                continue
                
            # Read bytes
            try:
                with open(filepath, "rb") as f:
                    data = f.read()
            except Exception as e:
                print(f" - Error reading '{filename}': {e}. Skipping.")
                continue
                
            # Check if media is already attached
            attached = session.scalar(
                select(EntityMedia).where(
                    EntityMedia.campaign_id == campaign_id,
                    EntityMedia.entity_id == entity.id,
                    EntityMedia.caption == caption
                )
            )
            if attached:
                print(f" - Image '{filename}' is already attached to {etype} '{ename}' as '{caption}'.")
                continue
                
            print(f" - Seeding '{filename}' -> {etype} '{ename}' ({caption})...")
            
            # Store bytes
            media = store_media_bytes(
                session, campaign_id, data, filename=filename, kind="image"
            )
            
            # Find next sort order
            next_order = session.execute(
                select(func.coalesce(func.max(EntityMedia.sort_order), -1) + 1).where(
                    EntityMedia.entity_id == entity.id
                )
            ).scalar_one()
            
            # Attach
            att = EntityMedia(
                id=new_id(),
                campaign_id=campaign_id,
                entity_id=entity.id,
                media_id=media.id,
                caption=caption,
                sort_order=int(next_order),
                created_at_real=now_real_iso()
            )
            session.add(att)
            session.commit()
            
        print("Image seeding complete.")

if __name__ == "__main__":
    main()
