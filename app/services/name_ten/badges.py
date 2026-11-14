"""Badges a list earns. Every badge is a compliment: none of them ranks taste.

Pure functions over the play's findings and items; the judge and the share
card read the same records.
"""

from __future__ import annotations

SETTLED = 20  # lists before a play for comparative badges to mean anything

BADGES = {
    "uncharted": ("Uncharted pair", "Put two books side by side that nobody here had paired before."),
    "own_shelf": ("Own shelf", "No earlier list shares more than two of your ten."),
    "excavator": ("Excavator", "Named three or more real books these shelves don't hold yet."),
    "canon": ("Keeper of the canon", "Stood by a book one in four lists name, and kept the rest your own."),
    "resident": ("Resident", "Seven or more of your ten are on these shelves, ready to read."),
    "early_hand": ("Early hand", "Named a ten before the game had two hundred lists."),
}
SHOWN = 3


def earned(facts: dict, items: list[dict]) -> list[dict]:
    """The badges for one play, most distinctive first, at most SHOWN."""
    settled = facts.get("lists_before", 0) >= SETTLED
    keys = []
    pair = facts.get("rarest_pair") or {}
    if pair.get("never_seen"):
        keys.append("uncharted")
    if settled and facts.get("closest_shared", 10) <= 2:
        keys.append("own_shelf")
    if sum(1 for item in items if item.get("status") == "finder") >= 3:
        keys.append("excavator")
    common = facts.get("most_common") or {}
    if settled and common and common.get("one_in", 99) <= 4 and facts.get("closest_shared", 10) <= 4:
        keys.append("canon")
    if sum(1 for item in items if item.get("status") == "library") >= 7:
        keys.append("resident")
    if facts.get("early"):
        keys.append("early_hand")
    return [{"key": key, "name": BADGES[key][0], "line": BADGES[key][1]} for key in keys[:SHOWN]]
