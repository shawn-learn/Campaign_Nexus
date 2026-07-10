"""NPC dynamics: location history, status, knowledge, itineraries (FR-6).

A top-layer context (like the playbook): it mints NPC entities in the wiki, resolves session
spans from the chronicle, and registers a ``move_npc`` action + an itinerary materializer
with the time engine — none of which the sibling contexts below may do for themselves.
"""
