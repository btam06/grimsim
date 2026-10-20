from app.list_rules import AllyRule

FACTION_NAME = "Drukhari"

# Corsairs and Travelling Players: a Drukhari army can include HARLEQUINS and
# ANHRATHE units (from Aeldari), up to 250/500/750 pts at Incursion/Strike
# Force/Onslaught, and none of their models can be given Enhancements.
ALLY_RULES = [
    AllyRule(
        host_faction=FACTION_NAME,
        ally_faction="Aeldari",
        model_keywords=("HARLEQUINS", "ANHRATHE"),
        points_limits={1000: 250, 2000: 500, 3000: 750},
        enhancements=False,
    ),
]
