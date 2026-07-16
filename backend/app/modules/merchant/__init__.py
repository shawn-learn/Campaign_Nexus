"""Merchant module — shops that sell equipment to the party.

A ``Merchant`` is a wiki ``Entity`` of type ``"merchant"`` (so it gets an article,
search, tags, and backlinks) optionally linked to the shopkeeper NPC and/or the
storefront location. Its ``MerchantStock`` lines draw from the shared equipment
library; buying imports the template into the campaign and hands the party a copy,
deducting gold. Selling back removes a party-held copy and credits gold.
"""
