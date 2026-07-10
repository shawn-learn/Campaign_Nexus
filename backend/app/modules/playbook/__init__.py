"""Playbook context (docs/04, §6.6): party, and later quests/encounters/combat.

The orchestration layer — it may call *into* the time and rules engines (advancing the
clock, applying rest rules) and campaign, but nothing imports it. Sits above the sibling
contexts in the module layering.
"""
