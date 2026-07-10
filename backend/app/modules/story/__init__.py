"""The branching story engine (FR-4): flags, story nodes/edges, conditions, consequences.

Top of the module stack — it reaches *down* into the graph (wiki), quests (playbook), NPCs
(npcs) and flags (campaign) to evaluate conditions and run consequences, so it sits above the
sibling contexts in the import-linter layering. The GM stays the author: conditions are
evaluated on demand to *suggest* the next beat, never to fire it automatically (FR-4.4).
"""
