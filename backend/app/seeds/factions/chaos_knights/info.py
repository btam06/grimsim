from app.list_rules import AllyRule

FACTION_NAME = "Chaos Knights"

ALLY_RULES = [
    # Iconoclast Fiefdom's Wretched Thralls: DAMNED units (see Codex: Chaos
    # Space Marines), up to 500 points of them.
    AllyRule(
        host_faction=FACTION_NAME,
        ally_faction="Chaos Space Marines",
        model_keywords=("DAMNED",),
        points_limits={1000: 500, 2000: 500},
        detachment="Iconoclast Fiefdom",
    ),
]
