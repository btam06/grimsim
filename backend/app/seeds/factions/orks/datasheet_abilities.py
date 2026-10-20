from app.combat_rules.conditions import RILED_UP_RANGED_CRITICAL_HIT
from app.combat_rules.effects import ADD_EXTRA_HIT

# Orks datasheet abilities - see app/seeds/datasheet_abilities.py for
# what each of these holds. Core abilities (e.g. Stealth) are defined there.

# (name, description, [condition keywords], [effect keywords])
ENTRIES = [
    (
        "Even More Dakka",
        "If this unit is riled up, this unit's ranged attacks have [SUSTAINED HITS 1].",
        [RILED_UP_RANGED_CRITICAL_HIT],
        [ADD_EXTRA_HIT],
    ),
]

