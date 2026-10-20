from sqlalchemy.ext.asyncio import AsyncSession

from app.seeds import (
    base_sizes,
    conditions,
    datasheet_abilities,
    dispositions,
    effects,
    factions,
    missions,
    stratagems,
    wargear_abilities,
    weapon_abilities,
)

# To seed another table on startup: add a module here with a NAMES list and an
# async def seed(session) function (see dispositions.py), then
# register its `seed` function below.
#
# Everything faction-specific lives in app/seeds/factions/, one folder per
# faction (info.py, abilities.py - see that package's __init__.py), with its
# data (keywords, units, detachments, datasheets) in app/data/factions/.
# factions.seed creates the Faction rows from each info.py, and
# seed_abilities/seed_keywords/seed_units/seed_detachments fill in the rest for every
# faction, so they must run after factions.seed (and seed_detachments after
# dispositions.seed, since it looks dispositions up by name; seed_enhancements
# and seed_detachment_rules after seed_detachments, seed_keywords and the
# ability seeds). seed_datasheets
# creates full models/weapons and must run after keywords, weapon abilities,
# faction abilities and base sizes, all of which it references by name.
#
# conditions.seed/effects.seed populate the hardcoded condition/effect catalog
# (see app/combat_rules/) that WeaponAbility/WargearAbility/DatasheetAbility
# rows reference; weapon_abilities.seed/wargear_abilities.seed/
# datasheet_abilities.seed build abilities from them (each with an ENTRIES
# list of (name, description, condition keywords, effect keywords)), so all
# three must run after conditions.seed/effects.seed.
#
# stratagems.seed loads stratagems (core, and detachment ones) from a local,
# uncommitted data file if present (see app/seeds/stratagems.py); it must run
# after keywords, conditions, effects and detachments are seeded.
#
# missions.seed loads primary/secondary mission cards from a local, uncommitted
# data file if present (see app/seeds/missions.py); it must run after
# dispositions.seed.
SEED_FUNCS = [
    dispositions.seed,
    base_sizes.seed,
    missions.seed,
    factions.seed,
    factions.seed_abilities,
    factions.seed_keywords,
    conditions.seed,
    effects.seed,
    weapon_abilities.seed,
    wargear_abilities.seed,
    datasheet_abilities.seed,
    factions.seed_units,
    factions.seed_detachments,
    factions.seed_enhancements,
    factions.seed_detachment_rules,
    factions.seed_datasheets,
    stratagems.seed,
]


async def run_all(session: AsyncSession) -> None:
    for seed_func in SEED_FUNCS:
        await seed_func(session)
