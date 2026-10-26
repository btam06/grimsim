from app.list_rules import imperial_allies

FACTION_NAME = "Space Marines"

# Imperial Agents and Imperial Knights units can join its lists.
ALLY_RULES = imperial_allies(FACTION_NAME)

# What its lists select (a list can, or not), and the keyword each option
# gives every one of the list's models with KEYWORD_HOLDERS - a model with one
# of these keywords of its own can only be in a list of that option (e.g.
# Roboute Guilliman, ULTRAMARINES) - unless one of the list's detachments lets
# it in anyway (`allies`: the option's keyword, the detachment, and the most
# points of such units the list can include - e.g. Deathwatch Support's
# Deathwatch Allies). A model let in like that keeps its own option's keyword
# and isn't given the list's, and can't be the list's WARLORD.
SUBFACTION = {
    "label": "Chapter",
    "keyword_holders": "ADEPTUS ASTARTES",
    "options": {"Ultramarines": "ULTRAMARINES", "Deathwatch": "DEATHWATCH"},
    "allies": [{"keyword": "DEATHWATCH", "detachment": "Deathwatch Support", "points": 500}],
}

# Detachments whose units with one of these keywords can only take that
# detachment's enhancements and upgrades, in a list that has taken it:
# {detachment name: (keyword, ...)} - e.g. Deathwatch Allies' KILL TEAM units.
EXCLUSIVE_ENHANCEMENTS = {"Deathwatch Support": ("KILL TEAM",)}
