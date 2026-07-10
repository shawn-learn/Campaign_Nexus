"""The Atlas — interactive maps (docs/04 §6, docs/05 §7.9).

A ``map`` is a wiki entity (entity_type 'map') with an image-backed extension row, plus
child ``map_marker`` records that each optionally target an entity (peek) or a child map
(drill-down). This context sits in the top orchestration layer alongside playbook: it may
reach down into wiki to mint map entities and resolve marker targets, but nothing imports it.
"""
